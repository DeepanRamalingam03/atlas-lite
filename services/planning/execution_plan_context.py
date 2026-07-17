from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.planning.models import (
    ExecutionPlan,
    PlanTask,
)
from core.planning.planner import (
    ProjectPlanner,
)


class ExecutionPlanner(Protocol):
    def create_plan(
        self,
        goal: str,
    ) -> ExecutionPlan:
        ...


@dataclass(slots=True, frozen=True)
class ExecutionPlanContext:
    goal: str
    task_count: int
    rendered_context: str


class ExecutionPlanContextService:
    """
    Builds deterministic planning context for one Atlas pipeline workflow.

    The plan guides manager, worker, validation, and review inside a single
    atomic autonomous workflow. Plan steps are not independently released
    or converted into separate roadmap tasks.

    This prevents analysis-only or review-only steps from being executed as
    standalone repository-changing workflows.
    """

    def __init__(
        self,
        planner: ExecutionPlanner | None = None,
        *,
        max_tasks: int = 12,
        max_characters: int = 12_000,
    ) -> None:
        if max_tasks < 1:
            raise ValueError(
                "max_tasks must be at least 1."
            )

        if max_tasks > 50:
            raise ValueError(
                "max_tasks cannot exceed 50."
            )

        if max_characters < 1_000:
            raise ValueError(
                "max_characters must be at least 1000."
            )

        self.planner = (
            planner or ProjectPlanner()
        )
        self.max_tasks = max_tasks
        self.max_characters = max_characters

    def build(
        self,
        goal: str,
    ) -> ExecutionPlanContext:
        cleaned_goal = " ".join(
            goal.split()
        )

        if not cleaned_goal:
            raise ValueError(
                "Planning goal cannot be empty."
            )

        plan = self.planner.create_plan(
            cleaned_goal
        )

        tasks = list(plan.tasks)

        if not tasks:
            raise RuntimeError(
                "Project planner returned no tasks."
            )

        if len(tasks) > self.max_tasks:
            raise RuntimeError(
                "Project planner exceeded the configured "
                f"task limit: {len(tasks)} > "
                f"{self.max_tasks}."
            )

        self._validate_tasks(tasks)

        rendered = self._render(
            goal=cleaned_goal,
            tasks=tasks,
        )

        return ExecutionPlanContext(
            goal=cleaned_goal,
            task_count=len(tasks),
            rendered_context=self._bound(
                rendered
            ),
        )

    def _validate_tasks(
        self,
        tasks: list[PlanTask],
    ) -> None:
        identifiers = [
            task.task_id
            for task in tasks
        ]

        if len(identifiers) != len(
            set(identifiers)
        ):
            raise RuntimeError(
                "Execution plan contains duplicate task IDs."
            )

        known: set[int] = set()

        for task in tasks:
            if task.task_id < 1:
                raise RuntimeError(
                    "Execution plan task IDs "
                    "must be positive."
                )

            if not task.title.strip():
                raise RuntimeError(
                    "Execution plan contains "
                    "an empty task title."
                )

            if not task.description.strip():
                raise RuntimeError(
                    "Execution plan contains "
                    "an empty task description."
                )

            duplicate_dependencies = (
                len(task.depends_on)
                != len(set(task.depends_on))
            )

            if duplicate_dependencies:
                raise RuntimeError(
                    "Execution plan contains duplicate "
                    f"dependencies for task {task.task_id}."
                )

            if task.task_id in task.depends_on:
                raise RuntimeError(
                    "Execution plan task cannot "
                    "depend on itself."
                )

            missing_or_forward = [
                dependency
                for dependency in task.depends_on
                if dependency not in known
            ]

            if missing_or_forward:
                raise RuntimeError(
                    "Execution plan contains missing "
                    "or forward dependencies for task "
                    f"{task.task_id}: "
                    + ", ".join(
                        str(value)
                        for value
                        in missing_or_forward
                    )
                )

            known.add(task.task_id)

    @staticmethod
    def _render(
        *,
        goal: str,
        tasks: list[PlanTask],
    ) -> str:
        lines = [
            "VERIFIED EXECUTION PLAN",
            "=======================",
            f"Original goal: {goal}",
            f"Task count: {len(tasks)}",
            "",
            "EXECUTION RULES",
            "===============",
            "- Treat this as one atomic repository workflow.",
            "- Follow the steps in dependency order.",
            "- Do not create unrelated files or features.",
            "- Repository grounding remains the source of truth.",
            "- Analysis and review steps do not themselves require files.",
            "- Implement only changes required by the original goal.",
            "- Add or update tests when behavior changes.",
            "- Validate the complete staged result before approval.",
            "- If a plan assumption conflicts with repository evidence, "
            "repository evidence wins.",
            "",
            "ORDERED TASKS",
            "=============",
        ]

        for task in tasks:
            dependencies = (
                ", ".join(
                    str(value)
                    for value in task.depends_on
                )
                if task.depends_on
                else "none"
            )

            lines.extend(
                [
                    "",
                    (
                        f"Task {task.task_id}: "
                        f"{task.title.strip()}"
                    ),
                    (
                        "Depends on: "
                        f"{dependencies}"
                    ),
                    (
                        "Instruction: "
                        f"{task.description.strip()}"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "EXPECTED EXECUTION BEHAVIOUR",
                "============================",
                "The manager must convert this plan into one precise "
                "worker instruction. The worker must return only the "
                "requested staged file changes. Validation and manager "
                "review must assess the integrated result against the "
                "original architect goal and this plan.",
            ]
        )

        return "\n".join(lines)

    def _bound(
        self,
        rendered: str,
    ) -> str:
        if len(rendered) <= self.max_characters:
            return rendered

        notice = (
            "\n\nPLANNING CONTEXT TRUNCATED\n"
            "==========================\n"
            "The verified beginning of the deterministic "
            "execution plan was retained."
        )

        available = (
            self.max_characters
            - len(notice)
        )

        return (
            rendered[:available].rstrip()
            + notice
        )


__all__ = [
    "ExecutionPlanContext",
    "ExecutionPlanContextService",
    "ExecutionPlanner",
]
