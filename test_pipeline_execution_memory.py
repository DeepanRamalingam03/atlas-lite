from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from orchestrator.pipeline import AtlasPipeline
from services.execution_memory.workflow_memory import (
    WorkflowExecutionMemory,
)
from testing.runner import StagingTestResult


class CapturingMemory(WorkflowExecutionMemory):
    instances: list["CapturingMemory"] = []

    def __init__(self) -> None:
        super().__init__()
        self.__class__.instances.append(self)


class FakeManager:
    def __init__(
        self,
        decisions: list[
            tuple[bool, str, str]
        ],
    ) -> None:
        self.decisions = decisions
        self.review_calls = 0

    def create_worker_prompt(
        self,
        goal: str,
    ) -> str:
        return "Implement the request."

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        index = min(
            self.review_calls,
            len(self.decisions) - 1,
        )

        approved, reason, fix = (
            self.decisions[index]
        )

        self.review_calls += 1

        decision = (
            "APPROVED"
            if approved
            else "REJECTED"
        )

        return (
            f"DECISION: {decision}\n\n"
            f"REASON:\n{reason}\n\n"
            f"FIX_INSTRUCTION:\n{fix}"
        )


class FakeWorker:
    def __init__(
        self,
        outputs: list[str],
    ) -> None:
        self.outputs = outputs
        self.prompts: list[str] = []

    def execute(
        self,
        prompt: str,
    ) -> str:
        self.prompts.append(prompt)

        index = min(
            len(self.prompts) - 1,
            len(self.outputs) - 1,
        )

        return self.outputs[index]


class FakePromptBuilder:
    def build_initial_prompt(
        self,
        goal: str,
        manager_instruction: str,
    ) -> str:
        return (
            f"INITIAL\n{goal}\n"
            f"{manager_instruction}"
        )

    def build_retry_prompt(
        self,
        *,
        goal: str,
        manager_instruction: str,
        rejection_reason: str,
        fix_instruction: str,
        test_output: str,
        iteration: int,
    ) -> str:
        return (
            f"RETRY {iteration}\n"
            f"{rejection_reason}\n"
            f"{fix_instruction}\n"
            f"{test_output}"
        )


class FakeParser:
    def parse(
        self,
        output: str,
    ) -> tuple[str, list]:
        if output == "INVALID":
            raise ValueError(
                "Invalid worker output."
            )

        path = (
            "feature.py"
            if "first" in output
            else "feature_fixed.py"
        )

        return (
            output,
            [
                SimpleNamespace(
                    path=path,
                    content="content",
                )
            ],
        )


class FakeReviewParser:
    def parse(
        self,
        review: str,
    ) -> SimpleNamespace:
        approved = (
            "DECISION: APPROVED"
            in review
        )

        reason = (
            review.split(
                "REASON:\n",
                1,
            )[1]
            .split(
                "\n\nFIX_INSTRUCTION:",
                1,
            )[0]
            .strip()
        )

        fix = review.split(
            "FIX_INSTRUCTION:\n",
            1,
        )[1].strip()

        return SimpleNamespace(
            approved=approved,
            reason=reason,
            fix_instruction=fix,
        )


class FakeWriter:
    def __init__(
        self,
        root: Path,
    ) -> None:
        self.staging_root = root

    def clear(self) -> None:
        return None

    def write_changes(
        self,
        changes: list,
    ) -> list[Path]:
        return [
            self.staging_root
            / change.path
            for change in changes
        ]


class SequenceRunner:
    def __init__(
        self,
        results: list[
            StagingTestResult
        ],
    ) -> None:
        self.results = results
        self.calls = 0

    def run_compile_check(
        self,
    ) -> StagingTestResult:
        index = min(
            self.calls,
            len(self.results) - 1,
        )

        self.calls += 1
        return self.results[index]


class PipelineExecutionMemoryTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        CapturingMemory.instances.clear()

        self.temporary = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temporary.name
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_first_attempt_has_no_memory(
        self,
    ) -> None:
        worker = FakeWorker(
            ["first approved"]
        )

        pipeline = self._pipeline(
            worker=worker,
            decisions=[
                (
                    True,
                    "Approved.",
                    "NONE",
                )
            ],
            test_results=[
                self._result(True)
            ],
            memory_enabled=True,
        )

        result = pipeline.execute(
            "Build feature."
        )

        self.assertTrue(result.approved)

        self.assertNotIn(
            "WORKFLOW EXECUTION MEMORY",
            worker.prompts[0],
        )

    def test_rejected_attempt_reaches_retry(
        self,
    ) -> None:
        worker = FakeWorker(
            [
                "first rejected",
                "second approved",
            ]
        )

        pipeline = self._pipeline(
            worker=worker,
            decisions=[
                (
                    False,
                    "Existing helper ignored.",
                    "Reuse the existing helper.",
                ),
                (
                    True,
                    "Approved.",
                    "NONE",
                ),
            ],
            test_results=[
                self._result(True),
                self._result(True),
            ],
            memory_enabled=True,
        )

        result = pipeline.execute(
            "Build feature."
        )

        self.assertTrue(result.approved)
        self.assertEqual(result.iterations, 2)

        retry = worker.prompts[1]

        self.assertIn(
            "WORKFLOW EXECUTION MEMORY",
            retry,
        )
        self.assertIn("ATTEMPT 1", retry)
        self.assertIn(
            "Existing helper ignored.",
            retry,
        )
        self.assertIn(
            "Reuse the existing helper.",
            retry,
        )
        self.assertIn("feature.py", retry)

    def test_processing_failure_reaches_retry(
        self,
    ) -> None:
        worker = FakeWorker(
            [
                "INVALID",
                "second approved",
            ]
        )

        pipeline = self._pipeline(
            worker=worker,
            decisions=[
                (
                    True,
                    "Approved.",
                    "NONE",
                )
            ],
            test_results=[
                self._result(True)
            ],
            memory_enabled=True,
        )

        result = pipeline.execute(
            "Build feature."
        )

        self.assertTrue(result.approved)

        retry = worker.prompts[1]

        self.assertIn(
            "WORKFLOW EXECUTION MEMORY",
            retry,
        )
        self.assertIn(
            "could not be processed",
            retry,
        )
        self.assertIn(
            "Changed paths: none",
            retry,
        )

    def test_memory_is_fresh_per_execute(
        self,
    ) -> None:
        pipeline = self._pipeline(
            worker=FakeWorker(
                ["first approved"]
            ),
            decisions=[
                (
                    True,
                    "Approved.",
                    "NONE",
                )
            ],
            test_results=[
                self._result(True)
            ],
            memory_enabled=True,
        )

        pipeline.execute("Goal one.")
        pipeline.execute("Goal two.")

        self.assertEqual(
            len(CapturingMemory.instances),
            2,
        )

        self.assertIsNot(
            CapturingMemory.instances[0],
            CapturingMemory.instances[1],
        )

    def test_memory_can_be_disabled(
        self,
    ) -> None:
        worker = FakeWorker(
            [
                "first rejected",
                "second approved",
            ]
        )

        pipeline = self._pipeline(
            worker=worker,
            decisions=[
                (
                    False,
                    "Rejected.",
                    "Fix.",
                ),
                (
                    True,
                    "Approved.",
                    "NONE",
                ),
            ],
            test_results=[
                self._result(True),
                self._result(True),
            ],
            memory_enabled=False,
        )

        result = pipeline.execute(
            "Legacy goal."
        )

        self.assertTrue(result.approved)

        self.assertNotIn(
            "WORKFLOW EXECUTION MEMORY",
            worker.prompts[1],
        )

    def test_approved_attempt_is_recorded(
        self,
    ) -> None:
        pipeline = self._pipeline(
            worker=FakeWorker(
                ["first approved"]
            ),
            decisions=[
                (
                    True,
                    "Approved.",
                    "NONE",
                )
            ],
            test_results=[
                self._result(True)
            ],
            memory_enabled=True,
        )

        result = pipeline.execute(
            "Build feature."
        )

        self.assertTrue(result.approved)

        latest = (
            CapturingMemory.instances[0]
            .latest()
        )

        self.assertIsNotNone(latest)

        assert latest is not None

        self.assertTrue(latest.test_success)
        self.assertTrue(
            latest.review_approved
        )
        self.assertEqual(
            latest.changed_paths,
            ("feature.py",),
        )

    def _pipeline(
        self,
        *,
        worker: FakeWorker,
        decisions: list[
            tuple[bool, str, str]
        ],
        test_results: list[
            StagingTestResult
        ],
        memory_enabled: bool,
    ) -> AtlasPipeline:
        return AtlasPipeline(
            manager=FakeManager(decisions),
            worker=worker,
            prompt_builder=FakePromptBuilder(),
            parser=FakeParser(),
            review_parser=FakeReviewParser(),
            workspace_writer=FakeWriter(
                self.root
            ),
            test_runner=SequenceRunner(
                test_results
            ),
            max_iterations=3,
            grounding_service=None,
            auto_ground_repository=False,
            planning_service=None,
            auto_plan=False,
            execution_memory_factory=(
                CapturingMemory
                if memory_enabled
                else None
            ),
            auto_execution_memory=False,
        )

    @staticmethod
    def _result(
        success: bool,
        output: str = "",
    ) -> StagingTestResult:
        return StagingTestResult(
            success=success,
            command=[],
            return_code=(
                0 if success else 1
            ),
            stdout=(
                output if success else ""
            ),
            stderr=(
                "" if success else output
            ),
        )


if __name__ == "__main__":
    unittest.main()
