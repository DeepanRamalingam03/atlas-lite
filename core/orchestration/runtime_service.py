from __future__ import annotations

import hashlib
import time
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
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class RuntimeCycleResult:
    status: RuntimeCycleStatus
    roadmap_selection: RoadmapSelection | None
    roadmap_task: RoadmapTask | None
    workflow_result: ContinuousRunResult | None
    resumed: bool
    message: str


class ContinuousRuntimeService:
    """
    Runs Atlas continuously from the persistent roadmap.

    Runtime flow:
    1. Acquire the single-instance process lock.
    2. Resume an interrupted RUNNING roadmap task when present.
    3. Otherwise select the highest-priority ready roadmap task.
    4. Execute or recover its deterministic workflow.
    5. Persist roadmap completion, failure, or human blocker state.
    6. Sleep and repeat.
    7. Stop when requested without inventing new work.
    """

    def __init__(
        self,
        roadmap_store: RoadmapTaskStore,
        roadmap_selector: RoadmapTaskSelector,
        orchestrator: ContinuousOrchestrator,
        recovery_manager: WorkflowRecoveryManager,
        *,
        process_lock: RuntimeProcessLock | None = None,
        user_id: int = 1,
        idle_seconds: float = 30.0,
        sleep_function: Callable[[float], None] = time.sleep,
    ) -> None:
        if user_id < 1:
            raise ValueError("user_id must be positive.")

        if idle_seconds < 0:
            raise ValueError(
                "idle_seconds cannot be negative."
            )

        self.roadmap_store = roadmap_store
        self.roadmap_selector = roadmap_selector
        self.orchestrator = orchestrator
        self.recovery_manager = recovery_manager
        self.process_lock = (
            process_lock or RuntimeProcessLock()
        )
        self.user_id = user_id
        self.idle_seconds = idle_seconds
        self.sleep_function = sleep_function

    def run_once(self) -> RuntimeCycleResult:
        running_tasks = [
            task
            for task in self.roadmap_store.list_all()
            if task.status == RoadmapTaskStatus.RUNNING
        ]

        if len(running_tasks) > 1:
            raise RuntimeError(
                "Multiple RUNNING roadmap tasks were found. "
                "Atlas requires a single active roadmap task."
            )

        if running_tasks:
            return self._execute_task(
                task=running_tasks[0],
                selection=None,
                resumed=True,
            )

        selection = self.roadmap_selector.start_next()

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
        if max_cycles is not None and max_cycles < 1:
            raise ValueError(
                "max_cycles must be at least 1."
            )

        resolved_stop_event = stop_event or Event()
        results: list[RuntimeCycleResult] = []
        cycle_count = 0

        with self.process_lock:
            while not resolved_stop_event.is_set():
                result = self.run_once()
                results.append(result)
                cycle_count += 1

                if (
                    max_cycles is not None
                    and cycle_count >= max_cycles
                ):
                    break

                if resolved_stop_event.is_set():
                    break

                self.sleep_function(
                    self.idle_seconds
                )

        return results

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
                self.orchestrator.workflow_store.load(
                    workflow_id
                )
            )

            if existing_workflow is None:
                workflow_result = (
                    self.orchestrator.run_goal(
                        user_id=self.user_id,
                        goal=task.goal,
                        workflow_id=workflow_id,
                        commit_message=(
                            self._commit_message(task)
                        ),
                    )
                )
            else:
                workflow_result = (
                    self.recovery_manager.recover(
                        workflow_id,
                        commit_message=(
                            self._commit_message(task)
                        ),
                    )
                )

            if workflow_result.completed:
                completed_task = (
                    self.roadmap_store.update_status(
                        task.task_id,
                        RoadmapTaskStatus.COMPLETED,
                    )
                )

                return RuntimeCycleResult(
                    status=RuntimeCycleStatus.COMPLETED,
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
                    workflow_result.workflow.summary.strip()
                    or "Human intervention is required."
                )

                blocked_task = (
                    self.roadmap_store.update_status(
                        task.task_id,
                        RoadmapTaskStatus.BLOCKED,
                        blocker_reason=blocker_reason,
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

            failed_task = (
                self.roadmap_store.update_status(
                    task.task_id,
                    RoadmapTaskStatus.FAILED,
                )
            )

            return RuntimeCycleResult(
                status=RuntimeCycleStatus.FAILED,
                roadmap_selection=selection,
                roadmap_task=failed_task,
                workflow_result=workflow_result,
                resumed=(
                    resumed
                    or workflow_result.resumed
                ),
                message=failure_reason,
            )

        except Exception as exc:
            current_task = self.roadmap_store.require(
                task.task_id
            )

            if (
                current_task.status
                == RoadmapTaskStatus.RUNNING
            ):
                current_task = (
                    self.roadmap_store.update_status(
                        task.task_id,
                        RoadmapTaskStatus.FAILED,
                    )
                )

            return RuntimeCycleResult(
                status=RuntimeCycleStatus.FAILED,
                roadmap_selection=selection,
                roadmap_task=current_task,
                workflow_result=None,
                resumed=resumed,
                message=(
                    f"{type(exc).__name__}: {exc}"
                ),
            )

    @staticmethod
    def _workflow_id(
        task_id: str,
    ) -> str:
        digest = hashlib.sha256(
            task_id.encode("utf-8")
        ).hexdigest()[:16]

        return f"roadmap-workflow-{digest}"

    @staticmethod
    def _commit_message(
        task: RoadmapTask,
    ) -> str:
        title = " ".join(
            task.title.split()
        )

        if len(title) > 60:
            title = title[:57].rstrip() + "..."

        return f"Atlas roadmap - {title}"
