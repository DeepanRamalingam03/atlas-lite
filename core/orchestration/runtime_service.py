from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from threading import Event
from typing import Callable

from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
    ContinuousRunResult,
)
from core.orchestration.recovery_manager import (
    WorkflowRecoveryManager,
)
from core.orchestration.retry_policy import (
    FailureClass,
    RuntimeRetryPolicy,
)
from core.orchestration.roadmap import (
    RoadmapSelection,
    RoadmapTask,
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from core.orchestration.runtime_lock import (
    RuntimeProcessLock,
)


class RuntimeCycleStatus(str, Enum):
    IDLE = "idle"
    COMPLETED = "completed"
    WAITING_FOR_HUMAN = "waiting_for_human"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class RuntimeCycleResult:
    status: RuntimeCycleStatus
    roadmap_selection: RoadmapSelection | None
    roadmap_task: RoadmapTask | None
    workflow_result: ContinuousRunResult | None
    resumed: bool
    message: str


CycleCallback = Callable[
    [RuntimeCycleResult],
    object,
]


class ContinuousRuntimeService:
    """
    Runs Atlas continuously from the persistent roadmap.

    Every cycle can be reported immediately through cycle_callback.
    Returned history is bounded to prevent long-running memory growth.
    """

    def __init__(
        self,
        roadmap_store: RoadmapTaskStore,
        roadmap_selector: RoadmapTaskSelector,
        orchestrator: ContinuousOrchestrator,
        recovery_manager: WorkflowRecoveryManager,
        *,
        process_lock: RuntimeProcessLock | None = None,
        retry_policy: RuntimeRetryPolicy | None = None,
        user_id: int = 1,
        idle_seconds: float = 30.0,
        sleep_function: Callable[[float], None] = time.sleep,
        cycle_callback: CycleCallback | None = None,
        history_limit: int = 100,
    ) -> None:
        if user_id < 1:
            raise ValueError(
                "user_id must be positive."
            )

        if idle_seconds < 0:
            raise ValueError(
                "idle_seconds cannot be negative."
            )

        if history_limit < 1:
            raise ValueError(
                "history_limit must be at least 1."
            )

        self.roadmap_store = roadmap_store
        self.roadmap_selector = roadmap_selector
        self.orchestrator = orchestrator
        self.recovery_manager = recovery_manager
        self.process_lock = (
            process_lock or RuntimeProcessLock()
        )
        self.retry_policy = (
            retry_policy
            or RuntimeRetryPolicy(
                max_attempts=1
            )
        )
        self.user_id = user_id
        self.idle_seconds = idle_seconds
        self.sleep_function = sleep_function
        self.cycle_callback = cycle_callback
        self.history_limit = history_limit

    def run_once(self) -> RuntimeCycleResult:
        running_tasks = [
            task
            for task in self.roadmap_store.list_all()
            if task.status
            == RoadmapTaskStatus.RUNNING
        ]

        if len(running_tasks) > 1:
            raise RuntimeError(
                "Multiple RUNNING roadmap tasks were found. "
                "Atlas requires a single active roadmap task."
            )

        if running_tasks:
            task = running_tasks[0]

            if not self.retry_policy.is_ready(
                task.task_id
            ):
                remaining = (
                    self.retry_policy
                    .seconds_until_ready(
                        task.task_id
                    )
                )

                return RuntimeCycleResult(
                    status=(
                        RuntimeCycleStatus
                        .RETRY_SCHEDULED
                    ),
                    roadmap_selection=None,
                    roadmap_task=task,
                    workflow_result=None,
                    resumed=True,
                    message=(
                        "Retry backoff active for task "
                        f"`{task.task_id}`. "
                        "Next attempt in "
                        f"{remaining:.1f} second(s)."
                    ),
                )

            self._prepare_retry_workflow(
                task
            )

            return self._execute_task(
                task=task,
                selection=None,
                resumed=True,
            )

        selection = (
            self.roadmap_selector.start_next()
        )

        if selection.task is None:
            return RuntimeCycleResult(
                status=RuntimeCycleStatus.IDLE,
                roadmap_selection=selection,
                roadmap_task=None,
                workflow_result=None,
                resumed=False,
                message=selection.message,
            )

        return self._execute_task(
            task=selection.task,
            selection=selection,
            resumed=False,
        )

    def run_forever(
        self,
        *,
        stop_event: Event | None = None,
        max_cycles: int | None = None,
    ) -> list[RuntimeCycleResult]:
        if (
            max_cycles is not None
            and max_cycles < 1
        ):
            raise ValueError(
                "max_cycles must be at least 1."
            )

        resolved_stop_event = (
            stop_event or Event()
        )

        results: deque[
            RuntimeCycleResult
        ] = deque(
            maxlen=self.history_limit
        )

        cycle_count = 0

        with self.process_lock:
            while not resolved_stop_event.is_set():
                result = self.run_once()
                results.append(result)
                cycle_count += 1

                if self.cycle_callback is not None:
                    self.cycle_callback(result)

                if (
                    max_cycles is not None
                    and cycle_count >= max_cycles
                ):
                    break

                if resolved_stop_event.is_set():
                    break

                self._sleep_between_cycles(
                    resolved_stop_event
                )

        return list(results)

    def _sleep_between_cycles(
        self,
        stop_event: Event,
    ) -> None:
        if self.sleep_function is time.sleep:
            stop_event.wait(
                self.idle_seconds
            )
            return

        self.sleep_function(
            self.idle_seconds
        )

    def _execute_task(
        self,
        task: RoadmapTask,
        selection: RoadmapSelection | None,
        resumed: bool,
    ) -> RuntimeCycleResult:
        workflow_id = self._workflow_id(
            task.task_id
        )

        try:
            existing_workflow = (
                self.orchestrator
                .workflow_store
                .load(workflow_id)
            )

            if existing_workflow is None:
                workflow_result = (
                    self.orchestrator.run_goal(
                        user_id=self.user_id,
                        goal=task.goal,
                        workflow_id=workflow_id,
                        commit_message=(
                            self._commit_message(
                                task
                            )
                        ),
                    )
                )
            else:
                workflow_result = (
                    self.recovery_manager.recover(
                        workflow_id,
                        commit_message=(
                            self._commit_message(
                                task
                            )
                        ),
                    )
                )

            if workflow_result.completed:
                self.retry_policy.clear_success(
                    task.task_id
                )

                completed_task = (
                    self.roadmap_store
                    .update_status(
                        task.task_id,
                        RoadmapTaskStatus.COMPLETED,
                    )
                )

                return RuntimeCycleResult(
                    status=(
                        RuntimeCycleStatus
                        .COMPLETED
                    ),
                    roadmap_selection=selection,
                    roadmap_task=completed_task,
                    workflow_result=workflow_result,
                    resumed=(
                        resumed
                        or workflow_result.resumed
                    ),
                    message=(
                        "Roadmap task completed: "
                        f"{completed_task.task_id} - "
                        f"{completed_task.title}"
                    ),
                )

            if workflow_result.waiting_for_human:
                blocker_reason = (
                    workflow_result
                    .workflow
                    .summary
                    .strip()
                    or (
                        "Human intervention "
                        "is required."
                    )
                )

                blocked_task = (
                    self.roadmap_store
                    .update_status(
                        task.task_id,
                        RoadmapTaskStatus.BLOCKED,
                        blocker_reason=(
                            blocker_reason
                        ),
                    )
                )

                return RuntimeCycleResult(
                    status=(
                        RuntimeCycleStatus
                        .WAITING_FOR_HUMAN
                    ),
                    roadmap_selection=selection,
                    roadmap_task=blocked_task,
                    workflow_result=workflow_result,
                    resumed=(
                        resumed
                        or workflow_result.resumed
                    ),
                    message=blocker_reason,
                )

            failure_reason = (
                workflow_result.error
                or workflow_result.workflow.error
                or "Atlas workflow failed."
            )

            return self._handle_failure(
                task=task,
                selection=selection,
                workflow_result=workflow_result,
                resumed=(
                    resumed
                    or workflow_result.resumed
                ),
                failure_reason=(
                    failure_reason
                ),
            )

        except Exception as exc:
            return self._handle_failure(
                task=task,
                selection=selection,
                workflow_result=None,
                resumed=resumed,
                failure_reason=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

    def _handle_failure(
        self,
        *,
        task: RoadmapTask,
        selection: RoadmapSelection | None,
        workflow_result: ContinuousRunResult | None,
        resumed: bool,
        failure_reason: str,
    ) -> RuntimeCycleResult:
        decision = (
            self.retry_policy.register_failure(
                task.task_id,
                failure_reason,
            )
        )

        if (
            decision
            .classification
            .failure_class
            == FailureClass.HUMAN_BLOCKER
        ):
            blocked_task = (
                self.roadmap_store.update_status(
                    task.task_id,
                    RoadmapTaskStatus.BLOCKED,
                    blocker_reason=failure_reason,
                )
            )

            return RuntimeCycleResult(
                status=(
                    RuntimeCycleStatus
                    .WAITING_FOR_HUMAN
                ),
                roadmap_selection=selection,
                roadmap_task=blocked_task,
                workflow_result=workflow_result,
                resumed=resumed,
                message=failure_reason,
            )

        if decision.retry:
            current_task = (
                self.roadmap_store.require(
                    task.task_id
                )
            )

            return RuntimeCycleResult(
                status=(
                    RuntimeCycleStatus
                    .RETRY_SCHEDULED
                ),
                roadmap_selection=selection,
                roadmap_task=current_task,
                workflow_result=workflow_result,
                resumed=resumed,
                message=(
                    f"{decision.message} "
                    "Attempt "
                    f"{decision.attempt_count}/"
                    f"{self.retry_policy.max_attempts}. "
                    f"Failure: {failure_reason}"
                ),
            )

        current_task = (
            self.roadmap_store.require(
                task.task_id
            )
        )

        if (
            current_task.status
            == RoadmapTaskStatus.RUNNING
        ):
            current_task = (
                self.roadmap_store
                .update_status(
                    task.task_id,
                    RoadmapTaskStatus.FAILED,
                )
            )

        return RuntimeCycleResult(
            status=RuntimeCycleStatus.FAILED,
            roadmap_selection=selection,
            roadmap_task=current_task,
            workflow_result=workflow_result,
            resumed=resumed,
            message=(
                f"{decision.message} "
                f"Failure: {failure_reason}"
            ),
        )

    def _prepare_retry_workflow(
        self,
        task: RoadmapTask,
    ) -> None:
        retry_state = (
            self.retry_policy
            .state_store
            .load(task.task_id)
        )

        if (
            retry_state is None
            or retry_state.attempt_count < 1
        ):
            return

        workflow_id = self._workflow_id(
            task.task_id
        )

        workflow = (
            self.orchestrator
            .workflow_store
            .load(workflow_id)
        )

        if workflow is None:
            return

        if workflow.status.value in {
            "failed",
            "rejected",
            "stopped",
        }:
            self.orchestrator.workflow_store.delete(
                workflow_id
            )

    @staticmethod
    def _workflow_id(
        task_id: str,
    ) -> str:
        digest = hashlib.sha256(
            task_id.encode("utf-8")
        ).hexdigest()[:16]

        return (
            f"roadmap-workflow-{digest}"
        )

    @staticmethod
    def _commit_message(
        task: RoadmapTask,
    ) -> str:
        title = " ".join(
            task.title.split()
        )

        if len(title) > 60:
            title = (
                title[:57].rstrip()
                + "..."
            )

        return (
            f"Atlas roadmap - {title}"
        )
