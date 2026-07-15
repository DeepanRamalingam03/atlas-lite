from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.file_change import FileChange
from managers.base_manager import BaseManager
from services.prompt_builder import PromptBuilder
from services.review_parser import ReviewDecision, ReviewParser
from services.worker_output_parser import WorkerOutputParser
from testing.runner import StagingTestResult, StagingTestRunner
from workers.base_worker import BaseWorker
from workspace.writer import WorkspaceWriter


@dataclass(slots=True)
class IterationRecord:
    iteration: int
    worker_prompt: str
    worker_output: str
    manager_review: str
    approved: bool
    test_success: bool


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
    history: list[IterationRecord] = field(default_factory=list)


class AtlasPipeline:
    """
    Atlas Lite autonomous development pipeline.

    Flow:
    Manager -> Prompt Builder -> Worker -> Parser -> Staging
    -> Test Runner -> Manager Review -> Intelligent Retry
    """

    def __init__(
        self,
        manager: BaseManager,
        worker: BaseWorker,
        prompt_builder: PromptBuilder,
        parser: WorkerOutputParser,
        review_parser: ReviewParser,
        workspace_writer: WorkspaceWriter,
        test_runner: StagingTestRunner,
        max_iterations: int = 3,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")

        self.manager = manager
        self.worker = worker
        self.prompt_builder = prompt_builder
        self.parser = parser
        self.review_parser = review_parser
        self.workspace_writer = workspace_writer
        self.test_runner = test_runner
        self.max_iterations = max_iterations

    def execute(self, goal: str) -> PipelineResult:
        cleaned_goal = goal.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        manager_instruction = self.manager.create_worker_prompt(
            cleaned_goal
        )

        worker_prompt = self.prompt_builder.build_initial_prompt(
            goal=cleaned_goal,
            manager_instruction=manager_instruction,
        )

        latest_summary = ""
        latest_changes: list[FileChange] = []
        latest_written_paths: list[Path] = []
        latest_test_result = self._empty_test_result()
        latest_review = ""
        history: list[IterationRecord] = []

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

                review_decision = self.review_parser.parse(
                    manager_review
                )

                approved = (
                    test_result.success
                    and review_decision.approved
                )

                history.append(
                    IterationRecord(
                        iteration=iteration,
                        worker_prompt=worker_prompt,
                        worker_output=worker_output,
                        manager_review=manager_review,
                        approved=approved,
                        test_success=test_result.success,
                    )
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
                        history=history,
                    )

                worker_prompt = self._build_retry_prompt(
                    goal=cleaned_goal,
                    manager_instruction=manager_instruction,
                    decision=review_decision,
                    test_result=test_result,
                    iteration=iteration + 1,
                )

            except Exception as exc:
                error_message = (
                    f"{type(exc).__name__}: {exc}"
                )

                latest_review = (
                    "DECISION: REJECTED\n\n"
                    "REASON:\n"
                    "The worker response could not be processed.\n\n"
                    "FIX_INSTRUCTION:\n"
                    "Return valid JSON matching the required schema with "
                    "complete file contents."
                )

                latest_test_result = StagingTestResult(
                    success=False,
                    command=[],
                    return_code=-1,
                    stdout="",
                    stderr=error_message,
                )

                history.append(
                    IterationRecord(
                        iteration=iteration,
                        worker_prompt=worker_prompt,
                        worker_output=worker_output,
                        manager_review=latest_review,
                        approved=False,
                        test_success=False,
                    )
                )

                worker_prompt = (
                    self.prompt_builder.build_retry_prompt(
                        goal=cleaned_goal,
                        manager_instruction=manager_instruction,
                        rejection_reason=(
                            "The worker response could not be processed."
                        ),
                        fix_instruction=(
                            "Return valid JSON matching the required schema "
                            "with complete file contents."
                        ),
                        test_output=error_message,
                        iteration=iteration + 1,
                    )
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
            history=history,
        )

    def _build_retry_prompt(
        self,
        goal: str,
        manager_instruction: str,
        decision: ReviewDecision,
        test_result: StagingTestResult,
        iteration: int,
    ) -> str:
        return self.prompt_builder.build_retry_prompt(
            goal=goal,
            manager_instruction=manager_instruction,
            rejection_reason=decision.reason,
            fix_instruction=decision.fix_instruction,
            test_output=(
                test_result.combined_output
                or "No test diagnostics were produced."
            ),
            iteration=iteration,
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
            "Output:\n"
            f"{test_result.combined_output or 'No output'}"
        )

    @staticmethod
    def _empty_test_result() -> StagingTestResult:
        return StagingTestResult(
            success=False,
            command=[],
            return_code=-1,
            stdout="",
            stderr="Pipeline did not produce a test result.",
        )
