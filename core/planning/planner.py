from __future__ import annotations

from core.planning.models import (
    ExecutionPlan,
    PlanTask,
)
from core.planning.task_decomposer import (
    TaskDecomposer,
)


class ProjectPlanner:
    """
    Creates validated, ordered execution plans.
    """

    def __init__(
        self,
        decomposer: TaskDecomposer | None = None,
    ) -> None:
        self.decomposer = decomposer or TaskDecomposer()

    def create_plan(
        self,
        goal: str,
    ) -> ExecutionPlan:
        cleaned_goal = goal.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        decomposed_tasks = self.decomposer.decompose(
            cleaned_goal
        )

        plan = ExecutionPlan(goal=cleaned_goal)

        for index, decomposed_task in enumerate(
            decomposed_tasks,
            start=1,
        ):
            plan.add_task(
                PlanTask(
                    task_id=index,
                    title=decomposed_task.title,
                    description=decomposed_task.description,
                    depends_on=[
                        dependency_index + 1
                        for dependency_index
                        in decomposed_task.depends_on_indexes
                    ],
                )
            )

        return plan
