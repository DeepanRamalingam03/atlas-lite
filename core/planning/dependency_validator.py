from __future__ import annotations

from core.planning.models import ExecutionPlan


class DependencyValidationError(ValueError):
    """Raised when an execution plan has invalid dependencies."""


class DependencyValidator:
    """
    Validates task dependency graphs before execution.
    """

    def validate(
        self,
        plan: ExecutionPlan,
    ) -> None:

        task_ids = {
            task.task_id
            for task in plan.tasks
        }

        for task in plan.tasks:

            if task.task_id in task.depends_on:
                raise DependencyValidationError(
                    f"Task {task.task_id} cannot depend on itself."
                )

            for dependency in task.depends_on:

                if dependency not in task_ids:
                    raise DependencyValidationError(
                        f"Task {task.task_id} depends on missing task {dependency}."
                    )

                if dependency >= task.task_id:
                    raise DependencyValidationError(
                        f"Task {task.task_id} has an invalid execution dependency."
                    )
