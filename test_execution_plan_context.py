from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.planning.models import (
    ExecutionPlan,
    PlanTask,
)
from services.planning.execution_plan_context import (
    ExecutionPlanContextService,
)


class FakePlanner:
    def __init__(
        self,
        tasks: list[PlanTask],
    ) -> None:
        self.tasks = tasks
        self.goals: list[str] = []

    def create_plan(
        self,
        goal: str,
    ) -> ExecutionPlan:
        self.goals.append(goal)

        return ExecutionPlan(
            goal=goal,
            tasks=list(self.tasks),
        )


class ExecutionPlanContextServiceTest(
    unittest.TestCase
):
    def test_existing_project_planner_is_rendered(
        self,
    ) -> None:
        context = (
            ExecutionPlanContextService()
            .build(
                "Add a Discord health command."
            )
        )

        self.assertGreater(
            context.task_count,
            1,
        )

        self.assertIn(
            "VERIFIED EXECUTION PLAN",
            context.rendered_context,
        )

        self.assertIn(
            "Design Discord integration changes",
            context.rendered_context,
        )

        self.assertIn(
            "Add or update automated tests",
            context.rendered_context,
        )

        self.assertIn(
            "Treat this as one atomic repository workflow",
            context.rendered_context,
        )

    def test_dependencies_are_rendered(
        self,
    ) -> None:
        planner = FakePlanner(
            [
                PlanTask(
                    task_id=1,
                    title="Inspect",
                    description="Inspect repository.",
                ),
                PlanTask(
                    task_id=2,
                    title="Implement",
                    description="Implement feature.",
                    depends_on=[1],
                ),
            ]
        )

        context = ExecutionPlanContextService(
            planner=planner
        ).build(
            "Build feature"
        )

        self.assertIn(
            "Task 2: Implement",
            context.rendered_context,
        )

        self.assertIn(
            "Depends on: 1",
            context.rendered_context,
        )

    def test_empty_goal_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            ExecutionPlanContextService().build(
                "   "
            )

    def test_empty_plan_is_rejected(
        self,
    ) -> None:
        service = ExecutionPlanContextService(
            planner=FakePlanner([])
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "returned no tasks",
        ):
            service.build(
                "Build feature"
            )

    def test_task_limit_is_enforced(
        self,
    ) -> None:
        tasks = [
            PlanTask(
                task_id=index,
                title=f"Task {index}",
                description="Work.",
                depends_on=(
                    [index - 1]
                    if index > 1
                    else []
                ),
            )
            for index in range(
                1,
                5,
            )
        ]

        service = ExecutionPlanContextService(
            planner=FakePlanner(tasks),
            max_tasks=3,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "task limit",
        ):
            service.build(
                "Build feature"
            )

    def test_duplicate_task_ids_are_rejected(
        self,
    ) -> None:
        service = ExecutionPlanContextService(
            planner=FakePlanner(
                [
                    PlanTask(
                        task_id=1,
                        title="One",
                        description="One.",
                    ),
                    PlanTask(
                        task_id=1,
                        title="Duplicate",
                        description="Duplicate.",
                    ),
                ]
            )
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "duplicate task IDs",
        ):
            service.build(
                "Build feature"
            )

    def test_forward_dependency_is_rejected(
        self,
    ) -> None:
        service = ExecutionPlanContextService(
            planner=FakePlanner(
                [
                    PlanTask(
                        task_id=1,
                        title="Invalid",
                        description="Invalid.",
                        depends_on=[2],
                    ),
                    PlanTask(
                        task_id=2,
                        title="Later",
                        description="Later.",
                    ),
                ]
            )
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "forward dependencies",
        ):
            service.build(
                "Build feature"
            )

    def test_context_is_bounded(
        self,
    ) -> None:
        planner = FakePlanner(
            [
                PlanTask(
                    task_id=1,
                    title="Large task",
                    description=(
                        "verified instruction "
                        * 500
                    ),
                )
            ]
        )

        context = ExecutionPlanContextService(
            planner=planner,
            max_characters=1_200,
        ).build(
            "Build feature"
        )

        self.assertLessEqual(
            len(context.rendered_context),
            1_200,
        )

        self.assertIn(
            "PLANNING CONTEXT TRUNCATED",
            context.rendered_context,
        )

    def test_plan_rules_prevent_independent_release(
        self,
    ) -> None:
        context = (
            ExecutionPlanContextService()
            .build(
                "Create typed utility."
            )
        )

        self.assertIn(
            "Analysis and review steps do not themselves require files",
            context.rendered_context,
        )

        self.assertIn(
            "one precise worker instruction",
            context.rendered_context,
        )


if __name__ == "__main__":
    unittest.main()
