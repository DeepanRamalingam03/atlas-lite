from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.file_change import FileChange
from managers.base_manager import BaseManager
from services.worker_output_parser import WorkerOutputParser
from testing.runner import StagingTestResult, StagingTestRunner
from workers.base_worker import BaseWorker
from workspace.writer import WorkspaceWriter


@dataclass(slots=True)
class PipelineResult:
    goal: str
    summary: str
    file_changes: list[FileChange]
    written_paths: list[Path]
    test_result: StagingTestResult
    manager_review: str
    approved: bool
    iterations: int


class AtlasPipeline:
    """
    Main Atlas Lite development pipeline.

    Flow:
    Manager -> Worker -> Parser -> Staging Workspace
    -> Test Runner -> Manager Review -> Approve or Retry
    """

    def __init__(
        self,
        manager: BaseManager,
        worker: BaseWorker,
        parser: WorkerOutputParser,
        workspace_writer: WorkspaceWriter,
        test_runner: StagingTestRunner,
        max_iterations: int = 3,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")

        self.manager = manager
        self.worker = worker
        self.parser = parser
        self.workspace_writer = workspace_writer
        self.test_runner = test_runner
        self.max_iterations = max_iterations

    def execute(self, goal: str) -> PipelineResult:
        cleaned_goal = goal.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        worker_prompt = self.manager.create_worker_prompt(cleaned_goal)

        latest_summary = ""
        latest_changes: list[FileChange] = []
        latest_written_paths: list[Path] = []
        latest_test_result = self._empty_test_result()
        latest_review = ""

        for iteration in range(1, self.max_iterations + 1):
            worker_output = self.worker.execute(worker_prompt)

            try:
                summary, file_changes = self.parser.parse(worker_output)

                self.workspace_writer.clear()

                written_paths = self.workspace_writer.write_changes(
                    file_changes
                )

                test_result = self.test_runner.run_compile_check()

                review_input = self._build_review_input(
                    worker_output=worker_output,
                    test_result=test_result,
                )

                manager_review = self.manager.review_worker_output(
                    goal=cleaned_goal,
                    worker_prompt=worker_prompt,
                    worker_output=review_input,
                )

                approved = (
                    test_result.success
                    and self._is_approved(manager_review)
                )

                latest_summary = summary
                latest_changes = file_changes
                latest_written_paths = written_paths
                latest_test_result = test_result
                latest_review = manager_review

                if approved:
                    return PipelineResult(
                        goal=cleaned_goal,
                        summary=summary,
                        file_changes=file_changes,
                        written_paths=written_paths,
                        test_result=test_result,
                        manager_review=manager_review,
                        approved=True,
                        iterations=iteration,
                    )

                correction = self._build_correction_instruction(
                    manager_review=manager_review,
                    test_result=test_result,
                )

            except Exception as exc:
                correction = (
                    "The previous worker response could not be processed.\n"
                    f"ERROR:\n{type(exc).__name__}: {exc}\n\n"
                    "Return corrected valid JSON using the required schema. "
                    "Include complete file contents only."
                )

                latest_review = correction
                latest_test_result = StagingTestResult(
                    success=False,
                    command=[],
                    return_code=-1,
                    stdout="",
                    stderr=str(exc),
                )

            worker_prompt = (
                f"{worker_prompt}\n\n"
                f"RETRY ITERATION {iteration}:\n"
                f"{correction}"
            )

        return PipelineResult(
            goal=cleaned_goal,
            summary=latest_summary,
            file_changes=latest_changes,
            written_paths=latest_written_paths,
            test_result=latest_test_result,
            manager_review=latest_review,
            approved=False,
            iterations=self.max_iterations,
        )

    @staticmethod
    def _build_review_input(
        worker_output: str,
        test_result: StagingTestResult,
    ) -> str:
        return (
            "WORKER JSON OUTPUT:\n"
            f"{worker_output}\n\n"
            "STAGING TEST RESULT:\n"
            f"Success: {test_result.success}\n"
            f"Return code: {test_result.return_code}\n"
            f"Output:\n{test_result.combined_output or 'No output'}"
        )

    @staticmethod
    def _build_correction_instruction(
        manager_review: str,
        test_result: StagingTestResult,
    ) -> str:
        diagnostics = (
            test_result.combined_output
            or "No test diagnostics were produced."
        )

        return (
            "Correct every issue identified below.\n\n"
            "MANAGER REVIEW:\n"
            f"{manager_review}\n\n"
            "TEST DIAGNOSTICS:\n"
            f"{diagnostics}\n\n"
            "Return valid JSON only with complete file contents."
        )

    @staticmethod
    def _is_approved(manager_review: str) -> bool:
        lines = manager_review.strip().splitlines()

        if not lines:
            return False

        return lines[0].strip().upper() == "DECISION: APPROVED"

    @staticmethod
    def _empty_test_result() -> StagingTestResult:
        return StagingTestResult(
            success=False,
            command=[],
            return_code=-1,
            stdout="",
            stderr="Pipeline did not produce a test result.",
        )
