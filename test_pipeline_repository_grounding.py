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


class FakeGroundingService:
    def __init__(
        self,
        context: str,
    ) -> None:
        self.context = context
        self.requests: list[str] = []

    def build(
        self,
        request: str,
    ) -> SimpleNamespace:
        self.requests.append(request)

        return SimpleNamespace(
            rendered_context=(
                self.context
            )
        )


class FailingGroundingService:
    def build(
        self,
        request: str,
    ) -> SimpleNamespace:
        raise RuntimeError(
            "Repository evidence unavailable."
        )


class FakeManager:
    def __init__(
        self,
        *,
        approve: bool = True,
    ) -> None:
        self.approve = approve
        self.created_goals: list[str] = []
        self.reviewed_goals: list[str] = []
        self.review_inputs: list[str] = []

    def create_worker_prompt(
        self,
        goal: str,
    ) -> str:
        self.created_goals.append(goal)

        return (
            "Implement only verified changes."
        )

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        self.reviewed_goals.append(goal)
        self.review_inputs.append(
            worker_output
        )

        if self.approve:
            return (
                "DECISION: APPROVED\n\n"
                "REASON:\n"
                "Grounded output is valid.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return (
            "DECISION: REJECTED\n\n"
            "REASON:\n"
            "The attempt repeated an "
            "unsupported assumption.\n\n"
            "FIX_INSTRUCTION:\n"
            "Use verified repository facts."
        )


class FakeWorker:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def execute(
        self,
        instruction: str,
    ) -> str:
        self.prompts.append(
            instruction
        )

        return (
            '{"summary":"Verified",'
            '"files":[]}'
        )


class FakePromptBuilder:
    def __init__(self) -> None:
        self.initial_goals: list[str] = []
        self.retry_test_outputs: list[str] = []

    def build_initial_prompt(
        self,
        goal: str,
        manager_instruction: str,
    ) -> str:
        self.initial_goals.append(goal)

        return (
            f"{goal}\n\n"
            f"{manager_instruction}"
        )

    def build_retry_prompt(
        self,
        goal: str,
        manager_instruction: str,
        rejection_reason: str,
        fix_instruction: str,
        test_output: str,
        iteration: int,
    ) -> str:
        self.retry_test_outputs.append(
            test_output
        )

        return (
            f"Retry {iteration}\n"
            f"{goal}\n"
            f"{rejection_reason}\n"
            f"{fix_instruction}\n"
            f"{test_output}"
        )


class FakeWorkerOutputParser:
    def parse(
        self,
        worker_output: str,
    ) -> tuple[str, list]:
        return "Verified", []


class FakeReviewParser:
    def parse(
        self,
        review: str,
    ) -> SimpleNamespace:
        approved = (
            "DECISION: APPROVED"
            in review
        )

        return SimpleNamespace(
            approved=approved,
            reason=(
                "Grounded output is valid."
                if approved
                else (
                    "Unsupported "
                    "assumption."
                )
            ),
            fix_instruction=(
                "NONE"
                if approved
                else (
                    "Use verified "
                    "repository facts."
                )
            ),
        )


class FakeWorkspaceWriter:
    def __init__(
        self,
        staging_root: Path,
    ) -> None:
        self.staging_root = (
            staging_root.resolve()
        )
        self.clear_count = 0

    def clear(self) -> None:
        self.clear_count += 1

    def write_changes(
        self,
        changes: list,
    ) -> list[Path]:
        return []


class FakeTestRunner:
    def __init__(
        self,
        output: str = (
            "No Python files found. "
            "Compile check skipped."
        ),
    ) -> None:
        self.output = output

    def run_compile_check(
        self,
    ) -> StagingTestResult:
        return StagingTestResult(
            success=True,
            command=[],
            return_code=0,
            stdout=self.output,
            stderr="",
        )


class PipelineRepositoryGroundingTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temporary.name
        )

        self.staging_root = (
            self.root / ".atlas_staging"
        )

        self.grounding_text = (
            "VERIFIED REPOSITORY GROUNDING\n"
            "Tracked file count: 199\n"
            "Tracked Python file count: 184\n"
            "Tracked test file count: 66"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_grounding_reaches_manager_and_worker(
        self,
    ) -> None:
        manager = FakeManager()
        worker = FakeWorker()
        prompt_builder = (
            FakePromptBuilder()
        )
        grounding = (
            FakeGroundingService(
                self.grounding_text
            )
        )

        pipeline = self._pipeline(
            manager=manager,
            worker=worker,
            prompt_builder=prompt_builder,
            grounding_service=grounding,
        )

        result = pipeline.execute(
            "Audit current repository."
        )

        self.assertTrue(
            result.approved
        )

        self.assertEqual(
            grounding.requests,
            [
                "Audit current repository."
            ],
        )

        self.assertIn(
            "Tracked Python file count: 184",
            manager.created_goals[0],
        )

        self.assertIn(
            "Tracked Python file count: 184",
            worker.prompts[0],
        )

        self.assertIn(
            "Tracked Python file count: 184",
            manager.reviewed_goals[0],
        )

    def test_review_separates_staging_from_repository(
        self,
    ) -> None:
        manager = FakeManager()

        pipeline = self._pipeline(
            manager=manager,
            grounding_service=(
                FakeGroundingService(
                    self.grounding_text
                )
            ),
        )

        result = pipeline.execute(
            "Create documentation."
        )

        self.assertTrue(
            result.approved
        )

        review_input = (
            manager.review_inputs[0]
        )

        self.assertIn(
            "Scope: temporary staged files",
            review_input,
        )

        self.assertIn(
            (
                "must not be used to infer "
                "that the main repository "
                "has no source code"
            ),
            review_input,
        )

        self.assertIn(
            "Tracked Python file count: 184",
            review_input,
        )

        self.assertIn(
            (
                "No Python files found. "
                "Compile check skipped."
            ),
            review_input,
        )

    def test_retry_contains_growing_evidence(
        self,
    ) -> None:
        manager = FakeManager(
            approve=False
        )

        prompt_builder = (
            FakePromptBuilder()
        )

        pipeline = self._pipeline(
            manager=manager,
            prompt_builder=prompt_builder,
            grounding_service=(
                FakeGroundingService(
                    self.grounding_text
                )
            ),
            max_iterations=2,
        )

        result = pipeline.execute(
            "Repair grounded documentation."
        )

        self.assertFalse(
            result.approved
        )

        self.assertEqual(
            result.iterations,
            2,
        )

        self.assertGreaterEqual(
            len(
                prompt_builder
                .retry_test_outputs
            ),
            1,
        )

        retry_evidence = (
            prompt_builder
            .retry_test_outputs[0]
        )

        self.assertIn(
            "CURRENT REPOSITORY EVIDENCE",
            retry_evidence,
        )

        self.assertIn(
            "Tracked Python file count: 184",
            retry_evidence,
        )

        self.assertIn(
            "FAILED ATTEMPT DIAGNOSTICS",
            retry_evidence,
        )

        self.assertIn(
            "Do not repeat a contradicted assumption",
            retry_evidence,
        )

    def test_grounding_failure_stops_before_worker(
        self,
    ) -> None:
        worker = FakeWorker()

        pipeline = self._pipeline(
            worker=worker,
            grounding_service=(
                FailingGroundingService()
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Repository evidence unavailable",
        ):
            pipeline.execute(
                "Unsafe ungrounded task."
            )

        self.assertEqual(
            worker.prompts,
            [],
        )

    def test_empty_grounding_is_rejected(
        self,
    ) -> None:
        pipeline = self._pipeline(
            grounding_service=(
                FakeGroundingService("   ")
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "returned empty evidence",
        ):
            pipeline.execute(
                "Inspect repository."
            )

    def test_grounding_is_bounded(
        self,
    ) -> None:
        large_context = (
            "verified-evidence\n"
            * 500
        )

        manager = FakeManager()

        pipeline = self._pipeline(
            manager=manager,
            grounding_service=(
                FakeGroundingService(
                    large_context
                )
            ),
            max_grounding_characters=1_200,
        )

        result = pipeline.execute(
            "Bound context."
        )

        self.assertTrue(
            result.approved
        )

        grounded_goal = (
            manager.created_goals[0]
        )

        self.assertIn(
            "GROUNDING CONTEXT TRUNCATED",
            grounded_goal,
        )

        self.assertLessEqual(
            len(
                grounded_goal
            ),
            1_500,
        )

    def test_pipeline_without_grounding_remains_compatible(
        self,
    ) -> None:
        manager = FakeManager()

        pipeline = self._pipeline(
            manager=manager,
            grounding_service=None,
            auto_ground_repository=False,
        )

        result = pipeline.execute(
            "Legacy compatible goal."
        )

        self.assertTrue(
            result.approved
        )

        self.assertEqual(
            manager.created_goals[0],
            "Legacy compatible goal.",
        )

    def _pipeline(
        self,
        *,
        manager: FakeManager | None = None,
        worker: FakeWorker | None = None,
        prompt_builder: (
            FakePromptBuilder | None
        ) = None,
        grounding_service=...,
        auto_ground_repository: bool = False,
        max_iterations: int = 1,
        max_grounding_characters: int = 100_000,
    ) -> AtlasPipeline:
        if grounding_service is ...:
            grounding_service = (
                FakeGroundingService(
                    self.grounding_text
                )
            )

        return AtlasPipeline(
            manager=(
                manager or FakeManager()
            ),
            worker=(
                worker or FakeWorker()
            ),
            prompt_builder=(
                prompt_builder
                or FakePromptBuilder()
            ),
            parser=(
                FakeWorkerOutputParser()
            ),
            review_parser=(
                FakeReviewParser()
            ),
            workspace_writer=(
                FakeWorkspaceWriter(
                    self.staging_root
                )
            ),
            test_runner=(
                FakeTestRunner()
            ),
            max_iterations=(
                max_iterations
            ),
            grounding_service=(
                grounding_service
            ),
            auto_ground_repository=(
                auto_ground_repository
            ),
            max_grounding_characters=(
                max_grounding_characters
            ),
        )


if __name__ == "__main__":
    unittest.main()
