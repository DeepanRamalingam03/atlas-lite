from __future__ import annotations

from dataclasses import dataclass

from core.execution.task_executor import (
    WorkerExecutionOutcome,
    WorkerTaskExecutor,
)
from core.planning.execution_coordinator import (
    ExecutionCoordinator,
    ExecutionProgress,
    PlanLifecycleStatus,
)
from core.planning.models import PlanTask
from core.planning.task_result_store import (
    TaskExecutionResult,
    TaskResultStore,
)


@dataclass(slots=True, frozen=True)
class PlanRunStep:
    plan_id: str
    task: PlanTask | None
    task_result: TaskExecutionResult | None
    progress: ExecutionProgress


class PlanRunner:
    """
    Executes persisted Atlas plans one task at a time.

    Flow:
    1. Load the next ready task.
    2. Mark it as running.
    3. Execute it through WorkerTaskExecutor.
    4. Persist the task result.
    5. Mark the task completed or failed.
    6. Return updated execution progress.
    """

    def __init__(
        self,
        coordinator: ExecutionCoordinator,
        task_executor: WorkerTaskExecutor,
        result_store: TaskResultStore | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.task_executor = task_executor
        self.result_store = (
            result_store or task_executor.result_store
        )

    def run_next(
        self,
        plan_id: str,
        project_context: str,
    ) -> PlanRunStep:
        initial_progress = self.coordinator.progress(
            plan_id
        )

        if initial_progress.status in {
            PlanLifecycleStatus.COMPLETED,
            PlanLifecycleStatus.FAILED,
            PlanLifecycleStatus.BLOCKED,
        }:
            return PlanRunStep(
                plan_id=plan_id,
                task=None,
                task_result=None,
                progress=initial_progress,
            )

        task = self.coordinator.start_next_task(
            plan_id
        )

        if task is None:
            return PlanRunStep(
                plan_id=plan_id,
                task=None,
                task_result=None,
                progress=self.coordinator.progress(
                    plan_id
                ),
            )

        previous_results = (
            self._render_previous_results(
                plan_id=plan_id,
                task=task,
            )
        )

        outcome = self.task_executor.execute(
            plan_id=plan_id,
            task=task,
            project_context=project_context,
            previous_results=previous_results,
        )

        self._apply_outcome(
            plan_id=plan_id,
            task=task,
            outcome=outcome,
        )

        return PlanRunStep(
            plan_id=plan_id,
            task=task,
            task_result=outcome.result,
            progress=self.coordinator.progress(
                plan_id
            ),
        )

    def run_until_pause(
        self,
        plan_id: str,
        project_context: str,
        max_steps: int = 100,
    ) -> list[PlanRunStep]:
        if max_steps < 1:
            raise ValueError(
                "max_steps must be at least 1."
            )

        steps: list[PlanRunStep] = []

        for _ in range(max_steps):
            step = self.run_next(
                plan_id=plan_id,
                project_context=project_context,
            )

            steps.append(step)

            if step.task is None:
                break

            if (
                step.task_result is not None
                and not step.task_result.success
            ):
                break

            if step.progress.status in {
                PlanLifecycleStatus.COMPLETED,
                PlanLifecycleStatus.FAILED,
                PlanLifecycleStatus.BLOCKED,
            }:
                break

        return steps

    def _render_previous_results(
        self,
        plan_id: str,
        task: PlanTask,
    ) -> str:
        results = self.result_store.list_for_plan(
            plan_id
        )

        dependency_ids = set(task.depends_on)

        dependency_results = [
            result
            for result in results
            if result.task_id in dependency_ids
        ]

        if not dependency_results:
            return "No dependency task results."

        sections: list[str] = []

        for result in dependency_results:
            sections.append(
                f"Task {result.task_id}\n"
                f"Success: {result.success}\n"
                f"Output:\n{result.output or 'No output.'}\n"
                f"Validation:\n"
                f"{result.validation_result or 'Not available.'}"
            )

        return "\n\n".join(sections)

    def _apply_outcome(
        self,
        plan_id: str,
        task: PlanTask,
        outcome: WorkerExecutionOutcome,
    ) -> None:
        if outcome.result.success:
            self.coordinator.complete_task(
                plan_id=plan_id,
                task_id=task.task_id,
            )
            return

        self.coordinator.fail_task(
            plan_id=plan_id,
            task_id=task.task_id,
        )
