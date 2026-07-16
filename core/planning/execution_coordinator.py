from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import uuid4

from core.planning.models import (
    ExecutionPlan,
    PlanTask,
    TaskStatus,
)
from core.planning.plan_state_store import PlanStateStore
from core.planning.planner import ProjectPlanner
from core.planning.task_scheduler import (
    TaskScheduler,
    TaskSchedulingError,
)


class PlanLifecycleStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(slots=True, frozen=True)
class ExecutionProgress:
    plan_id: str
    goal: str
    status: PlanLifecycleStatus
    total_tasks: int
    pending_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int
    blocked_tasks: int
    next_task_id: int | None


class ExecutionCoordinator:
    """
    Coordinates planning, scheduling, persistence, and task state changes.

    Responsibilities:
    - Create and persist execution plans.
    - Resume persisted plans.
    - Start the next ready task.
    - Mark tasks completed or failed.
    - Save every state transition.
    - Report plan progress and lifecycle status.
    """

    def __init__(
        self,
        planner: ProjectPlanner | None = None,
        scheduler: TaskScheduler | None = None,
        state_store: PlanStateStore | None = None,
    ) -> None:
        self.planner = planner or ProjectPlanner()
        self.scheduler = scheduler or TaskScheduler()
        self.state_store = (
            state_store or PlanStateStore()
        )

    def create_plan(
        self,
        goal: str,
        plan_id: str | None = None,
    ) -> tuple[str, ExecutionPlan]:
        cleaned_goal = goal.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        resolved_plan_id = (
            plan_id.strip()
            if plan_id is not None
            else self._generate_plan_id()
        )

        if not resolved_plan_id:
            raise ValueError("plan_id cannot be empty.")

        if self.state_store.exists(resolved_plan_id):
            raise ValueError(
                f"Plan already exists: {resolved_plan_id}"
            )

        plan = self.planner.create_plan(cleaned_goal)

        self.state_store.save(
            plan_id=resolved_plan_id,
            plan=plan,
        )

        return resolved_plan_id, plan

    def load_plan(
        self,
        plan_id: str,
    ) -> ExecutionPlan:
        plan = self.state_store.load(plan_id)

        if plan is None:
            raise KeyError(
                f"Execution plan does not exist: {plan_id}"
            )

        return plan

    def start_next_task(
        self,
        plan_id: str,
    ) -> PlanTask | None:
        plan = self.load_plan(plan_id)

        running_tasks = [
            task
            for task in plan.tasks
            if task.status == TaskStatus.RUNNING
        ]

        if running_tasks:
            raise TaskSchedulingError(
                "Cannot start another task while a task "
                "is already running."
            )

        next_task = self.scheduler.next_task(plan)

        if next_task is None:
            return None

        started_task = self.scheduler.mark_running(
            plan=plan,
            task_id=next_task.task_id,
        )

        self.state_store.save(
            plan_id=plan_id,
            plan=plan,
        )

        return started_task

    def complete_task(
        self,
        plan_id: str,
        task_id: int,
    ) -> PlanTask:
        plan = self.load_plan(plan_id)

        completed_task = self.scheduler.mark_completed(
            plan=plan,
            task_id=task_id,
        )

        self.state_store.save(
            plan_id=plan_id,
            plan=plan,
        )

        return completed_task

    def fail_task(
        self,
        plan_id: str,
        task_id: int,
    ) -> PlanTask:
        plan = self.load_plan(plan_id)

        failed_task = self.scheduler.mark_failed(
            plan=plan,
            task_id=task_id,
        )

        self.state_store.save(
            plan_id=plan_id,
            plan=plan,
        )

        return failed_task

    def retry_failed_task(
        self,
        plan_id: str,
        task_id: int,
    ) -> PlanTask:
        plan = self.load_plan(plan_id)

        task = self._get_task(
            plan=plan,
            task_id=task_id,
        )

        if task.status != TaskStatus.FAILED:
            raise TaskSchedulingError(
                f"Task {task_id} must be failed before retry."
            )

        task.status = TaskStatus.PENDING

        ready_ids = {
            ready_task.task_id
            for ready_task in self.scheduler.ready_tasks(plan)
        }

        if task_id not in ready_ids:
            task.status = TaskStatus.FAILED

            raise TaskSchedulingError(
                f"Task {task_id} cannot be retried because "
                "its dependencies are not completed."
            )

        self.state_store.save(
            plan_id=plan_id,
            plan=plan,
        )

        return task

    def progress(
        self,
        plan_id: str,
    ) -> ExecutionProgress:
        plan = self.load_plan(plan_id)

        total_tasks = len(plan.tasks)

        pending_tasks = sum(
            task.status == TaskStatus.PENDING
            for task in plan.tasks
        )

        running_tasks = sum(
            task.status == TaskStatus.RUNNING
            for task in plan.tasks
        )

        completed_tasks = sum(
            task.status == TaskStatus.COMPLETED
            for task in plan.tasks
        )

        failed_tasks = sum(
            task.status == TaskStatus.FAILED
            for task in plan.tasks
        )

        blocked_tasks = len(
            self.scheduler.blocked_tasks(plan)
        )

        next_task = self.scheduler.next_task(plan)

        lifecycle_status = self._resolve_status(
            plan=plan,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            running_tasks=running_tasks,
            blocked_tasks=blocked_tasks,
        )

        return ExecutionProgress(
            plan_id=plan_id,
            goal=plan.goal,
            status=lifecycle_status,
            total_tasks=total_tasks,
            pending_tasks=pending_tasks,
            running_tasks=running_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            blocked_tasks=blocked_tasks,
            next_task_id=(
                next_task.task_id
                if next_task is not None
                else None
            ),
        )

    def delete_plan(
        self,
        plan_id: str,
    ) -> None:
        self.state_store.delete(plan_id)

    def list_plan_ids(self) -> list[str]:
        return self.state_store.list_plan_ids()

    @staticmethod
    def _resolve_status(
        plan: ExecutionPlan,
        completed_tasks: int,
        failed_tasks: int,
        running_tasks: int,
        blocked_tasks: int,
    ) -> PlanLifecycleStatus:
        if plan.tasks and completed_tasks == len(plan.tasks):
            return PlanLifecycleStatus.COMPLETED

        if running_tasks > 0:
            return PlanLifecycleStatus.RUNNING

        if failed_tasks > 0:
            return PlanLifecycleStatus.FAILED

        if blocked_tasks > 0:
            return PlanLifecycleStatus.BLOCKED

        return PlanLifecycleStatus.PENDING

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

    @staticmethod
    def _generate_plan_id() -> str:
        return f"plan-{uuid4().hex[:12]}"
