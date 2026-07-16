from __future__ import annotations

from core.planning.dependency_validator import (
    DependencyValidator,
)
from core.planning.models import (
    ExecutionPlan,
    PlanTask,
    TaskStatus,
)


class TaskSchedulingError(RuntimeError):
    """Raised when task scheduling cannot continue safely."""


class TaskScheduler:
    """
    Selects executable tasks from a validated execution plan.

    A task is ready when:
    - its status is PENDING,
    - all dependency tasks are COMPLETED.

    Failed dependencies block dependent tasks.
    """

    def __init__(
        self,
        dependency_validator: DependencyValidator | None = None,
    ) -> None:
        self.dependency_validator = (
            dependency_validator or DependencyValidator()
        )

    def ready_tasks(
        self,
        plan: ExecutionPlan,
    ) -> list[PlanTask]:
        self.dependency_validator.validate(plan)

        tasks_by_id = {
            task.task_id: task
            for task in plan.tasks
        }

        ready: list[PlanTask] = []

        for task in plan.tasks:
            if task.status != TaskStatus.PENDING:
                continue

            dependency_tasks = [
                tasks_by_id[dependency_id]
                for dependency_id in task.depends_on
            ]

            if any(
                dependency.status == TaskStatus.FAILED
                for dependency in dependency_tasks
            ):
                continue

            if all(
                dependency.status == TaskStatus.COMPLETED
                for dependency in dependency_tasks
            ):
                ready.append(task)

        return ready

    def blocked_tasks(
        self,
        plan: ExecutionPlan,
    ) -> list[PlanTask]:
        self.dependency_validator.validate(plan)

        tasks_by_id = {
            task.task_id: task
            for task in plan.tasks
        }

        blocked: list[PlanTask] = []

        for task in plan.tasks:
            if task.status != TaskStatus.PENDING:
                continue

            dependency_tasks = [
                tasks_by_id[dependency_id]
                for dependency_id in task.depends_on
            ]

            if any(
                dependency.status == TaskStatus.FAILED
                for dependency in dependency_tasks
            ):
                blocked.append(task)

        return blocked

    def waiting_tasks(
        self,
        plan: ExecutionPlan,
    ) -> list[PlanTask]:
        ready_ids = {
            task.task_id
            for task in self.ready_tasks(plan)
        }

        blocked_ids = {
            task.task_id
            for task in self.blocked_tasks(plan)
        }

        return [
            task
            for task in plan.tasks
            if task.status == TaskStatus.PENDING
            and task.task_id not in ready_ids
            and task.task_id not in blocked_ids
        ]

    def next_task(
        self,
        plan: ExecutionPlan,
    ) -> PlanTask | None:
        ready = self.ready_tasks(plan)

        if not ready:
            return None

        return sorted(
            ready,
            key=lambda task: task.task_id,
        )[0]

    def mark_running(
        self,
        plan: ExecutionPlan,
        task_id: int,
    ) -> PlanTask:
        task = self._get_task(plan, task_id)

        if task.status != TaskStatus.PENDING:
            raise TaskSchedulingError(
                f"Task {task_id} must be pending before running."
            )

        ready_ids = {
            ready_task.task_id
            for ready_task in self.ready_tasks(plan)
        }

        if task_id not in ready_ids:
            raise TaskSchedulingError(
                f"Task {task_id} is not ready to run."
            )

        task.status = TaskStatus.RUNNING
        return task

    def mark_completed(
        self,
        plan: ExecutionPlan,
        task_id: int,
    ) -> PlanTask:
        task = self._get_task(plan, task_id)

        if task.status != TaskStatus.RUNNING:
            raise TaskSchedulingError(
                f"Task {task_id} must be running before completion."
            )

        task.status = TaskStatus.COMPLETED
        return task

    def mark_failed(
        self,
        plan: ExecutionPlan,
        task_id: int,
    ) -> PlanTask:
        task = self._get_task(plan, task_id)

        if task.status != TaskStatus.RUNNING:
            raise TaskSchedulingError(
                f"Task {task_id} must be running before failure."
            )

        task.status = TaskStatus.FAILED
        return task

    @staticmethod
    def _get_task(
        plan: ExecutionPlan,
        task_id: int,
    ) -> PlanTask:
        for task in plan.tasks:
            if task.task_id == task_id:
                return task

        raise TaskSchedulingError(
            f"Task {task_id} does not exist."
        )
