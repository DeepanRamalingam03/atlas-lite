from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DecomposedTask:
    title: str
    description: str
    depends_on_indexes: tuple[int, ...] = ()


class TaskDecomposer:
    """
    Converts a high-level software goal into ordered implementation tasks.

    This first version is deterministic. It gives Atlas a safe and
    predictable planning structure before AI-generated planning is enabled.
    """

    AUTH_KEYWORDS = {
        "auth",
        "authentication",
        "authorize",
        "authorization",
        "jwt",
        "login",
        "token",
    }

    TEST_KEYWORDS = {
        "test",
        "testing",
        "pytest",
        "unit test",
        "integration test",
    }

    DISCORD_KEYWORDS = {
        "discord",
        "bot",
        "command",
    }

    def decompose(
        self,
        goal: str,
    ) -> list[DecomposedTask]:
        cleaned_goal = self._clean_goal(goal)

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        normalized_goal = cleaned_goal.lower()

        tasks: list[DecomposedTask] = [
            DecomposedTask(
                title="Analyze current implementation",
                description=(
                    "Inspect the project knowledge, relevant files, "
                    f"existing architecture, and constraints for: {cleaned_goal}"
                ),
            ),
            DecomposedTask(
                title="Define implementation scope",
                description=(
                    "Identify required file changes, expected behavior, "
                    "validation rules, risks, and acceptance criteria."
                ),
                depends_on_indexes=(0,),
            ),
        ]

        if self._contains_any(
            normalized_goal,
            self.AUTH_KEYWORDS,
        ):
            tasks.extend(
                [
                    DecomposedTask(
                        title="Design authentication changes",
                        description=(
                            "Define the authentication flow, token lifecycle, "
                            "configuration, permissions, and security boundaries."
                        ),
                        depends_on_indexes=(1,),
                    ),
                    DecomposedTask(
                        title="Implement authentication components",
                        description=(
                            "Create or update authentication services, "
                            "token utilities, middleware, routes, and configuration."
                        ),
                        depends_on_indexes=(2,),
                    ),
                ]
            )

        elif self._contains_any(
            normalized_goal,
            self.DISCORD_KEYWORDS,
        ):
            tasks.extend(
                [
                    DecomposedTask(
                        title="Design Discord integration changes",
                        description=(
                            "Identify commands, event handlers, permissions, "
                            "message flow, and affected Discord gateway files."
                        ),
                        depends_on_indexes=(1,),
                    ),
                    DecomposedTask(
                        title="Implement Discord changes",
                        description=(
                            "Update the relevant Discord bot, command, "
                            "gateway, and manager integration code."
                        ),
                        depends_on_indexes=(2,),
                    ),
                ]
            )

        else:
            tasks.append(
                DecomposedTask(
                    title="Implement requested changes",
                    description=(
                        "Modify or create the required project files "
                        f"to complete: {cleaned_goal}"
                    ),
                    depends_on_indexes=(1,),
                )
            )

        implementation_index = len(tasks) - 1

        tasks.append(
            DecomposedTask(
                title="Add or update automated tests",
                description=(
                    "Create tests for the new behavior, failure paths, "
                    "edge cases, and regression protection."
                ),
                depends_on_indexes=(implementation_index,),
            )
        )

        test_index = len(tasks) - 1

        tasks.extend(
            [
                DecomposedTask(
                    title="Run deterministic validation",
                    description=(
                        "Run syntax checks, automated tests, static validation, "
                        "and inspect all failures."
                    ),
                    depends_on_indexes=(test_index,),
                ),
                DecomposedTask(
                    title="Review implementation",
                    description=(
                        "Review correctness, architecture compliance, security, "
                        "completeness, and requested behavior."
                    ),
                    depends_on_indexes=(len(tasks) - 1,),
                ),
                DecomposedTask(
                    title="Prepare changes for human approval",
                    description=(
                        "Generate a clear summary, changed-file list, "
                        "validation results, risks, and approval request."
                    ),
                    depends_on_indexes=(len(tasks) - 1,),
                ),
            ]
        )

        return tasks

    @staticmethod
    def _clean_goal(goal: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            goal,
        ).strip()

    @staticmethod
    def _contains_any(
        text: str,
        keywords: set[str],
    ) -> bool:
        return any(
            keyword in text
            for keyword in keywords
        )
