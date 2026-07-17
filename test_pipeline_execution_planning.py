from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from orchestrator.pipeline import (
    AtlasPipeline,
)
from testing.runner import (
    StagingTestResult,
)


class FakePlanningService:
    def __init__(
        self,
        rendered: str,
    ) -> None:
        self.rendered = rendered
        self.goals: list[str] = []

    def build(
        self,
        goal: str,
    ) -> SimpleNamespace:
        self.goals.append(goal)

        return SimpleNamespace(
            rendered_context=self.rendered,
        )


class FailingPlanningService:
    def build(
        self,
        goal: str,
    ) -> SimpleNamespace:
        raise RuntimeError(
            "Planning unavailable."
        )


class FakeManager:
    def __init__(self) -> None:
        self.created_goals: list[str] = []
        self.reviewed_goals: list[str] = []

    def create_worker_prompt(
        self,
        goal: str,
    ) -> str:
        self.created_goals.append(goal)
        return "Implement verified plan."

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        self.reviewed_goals.append(goal)

        return (
            "DECISION: APPROVED\n\n"
            "REASON:\n"
            "Plan completed.\n\n"
            "FIX_INSTRUCTION:\n"
            "NONE"
        )


class FakeWorker:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def execute(
        self,
        prompt: str,
    ) -> str:
        self.prompts.append(prompt)

        return (
            '{"summary":"planned",'
            '"files":[]}'
        )


class FakePromptBuilder:
    def build_initial_prompt(
        self,
        goal: str,
        manager_instruction: str,
    ) -> str:
        return (
            f"{goal}\n"
            f"{manager_instruction}"
        )

    def build_retry_prompt(
        self,
        **kwargs,
    ) -> str:
        return "retry"


class FakeParser:
    def parse(
        self,
        output: str,
    ) -> tuple[str, list]:
        return "planned", []


class FakeReviewParser:
    def parse(
        self,
        review: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            approved=True,
            reason="Approved.",
            fix_instruction="NONE",
        )


class FakeWriter:
    def __init__(
        self,
        staging_root: Path,
    ) -> None:
        self.staging_root = staging_root

    def clear(self) -> None:
        return None

    def write_changes(
        self,
        changes: list,
    ) -> list[Path]:
        return []


class FakeRunner:
    def run_compile_check(
        self,
    ) -> StagingTestResult:
        return StagingTestResult(
            success=True,
            command=[],
            return_code=0,
            stdout="Validation passed.",
            stderr="",
        )


class PipelineExecutionPlanningTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )

        self.staging_root = Path(
            self.temporary.name
        ) / ".atlas_staging"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_plan_reaches_manager_worker_and_review(
        self,
    ) -> None:
        manager = FakeManager()
        worker = FakeWorker()

        planning = FakePlanningService(
            "VERIFIED EXECUTION PLAN\nTask 1: Inspect"
        )

        pipeline = self._pipeline(
            manager=manager,
            worker=worker,
            planning_service=planning,
        )

        result = pipeline.execute(
            "Build feature."
        )

        self.assertTrue(result.approved)

        self.assertEqual(
            planning.goals,
            ["Build feature."],
        )

        self.assertIn(
            "VERIFIED EXECUTION PLAN",
            manager.created_goals[0],
        )

        self.assertIn(
            "Task 1: Inspect",
            worker.prompts[0],
        )

        self.assertIn(
            "VERIFIED EXECUTION PLAN",
            manager.reviewed_goals[0],
        )

    def test_planning_failure_stops_before_manager(
        self,
    ) -> None:
        manager = FakeManager()

        pipeline = self._pipeline(
            manager=manager,
            planning_service=(
                FailingPlanningService()
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Planning unavailable",
        ):
            pipeline.execute(
                "Build feature."
            )

        self.assertEqual(
            manager.created_goals,
            [],
        )

    def test_empty_planning_context_is_rejected(
        self,
    ) -> None:
        pipeline = self._pipeline(
            planning_service=(
                FakePlanningService("   ")
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "returned empty context",
        ):
            pipeline.execute(
                "Build feature."
            )

    def test_planning_can_be_disabled(
        self,
    ) -> None:
        manager = FakeManager()

        pipeline = self._pipeline(
            manager=manager,
            planning_service=None,
            auto_plan=False,
        )

        result = pipeline.execute(
            "Legacy feature."
        )

        self.assertTrue(result.approved)

        self.assertNotIn(
            "VERIFIED EXECUTION PLAN",
            manager.created_goals[0],
        )

    def _pipeline(
        self,
        *,
        manager: FakeManager | None = None,
        worker: FakeWorker | None = None,
        planning_service=...,
        auto_plan: bool = False,
    ) -> AtlasPipeline:
        if planning_service is ...:
            planning_service = (
                FakePlanningService(
                    "VERIFIED EXECUTION PLAN"
                )
            )

        return AtlasPipeline(
            manager=manager or FakeManager(),
            worker=worker or FakeWorker(),
            prompt_builder=FakePromptBuilder(),
            parser=FakeParser(),
            review_parser=FakeReviewParser(),
            workspace_writer=FakeWriter(
                self.staging_root
            ),
            test_runner=FakeRunner(),
            max_iterations=1,
            grounding_service=None,
            auto_ground_repository=False,
            planning_service=planning_service,
            auto_plan=auto_plan,
        )


if __name__ == "__main__":
    unittest.main()
