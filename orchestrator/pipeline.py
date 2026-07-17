from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Protocol,
)

from core.file_change import FileChange
from managers.base_manager import BaseManager
from services.project.repository_grounding_service import (
    RepositoryGroundingService,
)
from services.execution_memory.workflow_memory import (
    WorkflowExecutionMemory,
)
from services.planning.execution_plan_context import (
    ExecutionPlanContextService,
)
from services.prompt_builder import PromptBuilder
from services.review_parser import (
    ReviewDecision,
    ReviewParser,
)
from services.worker_output_parser import (
    WorkerOutputParser,
)
from testing.runner import (
    StagingTestResult,
    StagingTestRunner,
)
from workers.base_worker import BaseWorker
from workspace.writer import WorkspaceWriter


class GroundingService(Protocol):
    def build(
        self,
        request: str,
    ) -> Any:
        ...


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
    history: list[IterationRecord] = field(
        default_factory=list
    )


class AtlasPipeline:
    """
    Atlas Lite autonomous development pipeline.

    Flow:
    Verified repository grounding
    -> Manager
    -> Prompt Builder
    -> Worker
    -> Parser
    -> Staging
    -> Staging validation
    -> Manager review with repository evidence
    -> Evidence-aware retry preparation.

    Repository evidence and staging validation are deliberately separate.
    A staging workspace containing no Python files does not imply that the
    project repository contains no Python implementation.
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
        grounding_service: (
            GroundingService | None
        ) = None,
        auto_ground_repository: bool = True,
        max_grounding_characters: int = 100_000,
        planning_service: (
            ExecutionPlanContextService | None
        ) = None,
        auto_plan: bool = False,
        execution_memory_factory: (
            Callable[
                [],
                WorkflowExecutionMemory,
            ]
            | None
        ) = None,
        auto_execution_memory: bool = False,
    ) -> None:
        if max_iterations < 1:
            raise ValueError(
                "max_iterations must be at least 1."
            )

        if max_grounding_characters < 1_000:
            raise ValueError(
                "max_grounding_characters must be "
                "at least 1000."
            )

        self.manager = manager
        self.worker = worker
        self.prompt_builder = prompt_builder
        self.parser = parser
        self.review_parser = review_parser
        self.workspace_writer = workspace_writer
        self.test_runner = test_runner
        self.max_iterations = max_iterations
        self.max_grounding_characters = (
            max_grounding_characters
        )

        self.grounding_service = (
            grounding_service
            or self._auto_grounding_service(
                enabled=auto_ground_repository
            )
        )

        self.planning_service = (
            planning_service
            or (
                ExecutionPlanContextService()
                if auto_plan
                else None
            )
        )

        self.execution_memory_factory = (
            execution_memory_factory
            or (
                WorkflowExecutionMemory
                if auto_execution_memory
                else None
            )
        )

    def execute(
        self,
        goal: str,
    ) -> PipelineResult:
        cleaned_goal = goal.strip()

        if not cleaned_goal:
            raise ValueError(
                "Goal cannot be empty."
            )

        planning_context = (
            self._build_planning_context(
                cleaned_goal
            )
        )

        grounding_context = (
            self._build_grounding_context(
                cleaned_goal
            )
        )

        grounded_goal = (
            self._compose_grounded_goal(
                goal=cleaned_goal,
                planning_context=(
                    planning_context
                ),
                grounding_context=(
                    grounding_context
                ),
            )
        )

        manager_instruction = (
            self.manager
            .create_worker_prompt(
                grounded_goal
            )
        )

        worker_prompt = (
            self.prompt_builder
            .build_initial_prompt(
                goal=grounded_goal,
                manager_instruction=(
                    manager_instruction
                ),
            )
        )

        latest_summary = ""
        latest_changes: list[FileChange] = []
        latest_written_paths: list[Path] = []
        latest_test_result = (
            self._empty_test_result()
        )
        latest_review = ""
        history: list[IterationRecord] = []

        execution_memory = (
            self.execution_memory_factory()
            if self.execution_memory_factory
            is not None
            else None
        )

        for iteration in range(
            1,
            self.max_iterations + 1,
        ):
            worker_output = self.worker.execute(
                worker_prompt
            )

            try:
                summary, file_changes = (
                    self.parser.parse(
                        worker_output
                    )
                )

                self.workspace_writer.clear()

                written_paths = (
                    self.workspace_writer
                    .write_changes(
                        file_changes
                    )
                )

                test_result = (
                    self.test_runner
                    .run_compile_check()
                )

                review_input = (
                    self._build_review_input(
                        worker_output=(
                            worker_output
                        ),
                        test_result=(
                            test_result
                        ),
                        grounding_context=(
                            grounding_context
                        ),
                    )
                )

                manager_review = (
                    self.manager
                    .review_worker_output(
                        goal=grounded_goal,
                        worker_prompt=(
                            worker_prompt
                        ),
                        worker_output=(
                            review_input
                        ),
                    )
                )

                review_decision = (
                    self.review_parser.parse(
                        manager_review
                    )
                )

                approved = (
                    test_result.success
                    and review_decision.approved
                )

                if execution_memory is not None:
                    execution_memory.record(
                        iteration=iteration,
                        summary=summary,
                        changed_paths=(
                            change.path
                            for change
                            in file_changes
                        ),
                        test_success=(
                            test_result.success
                        ),
                        review_approved=(
                            review_decision.approved
                        ),
                        review_reason=(
                            review_decision.reason
                        ),
                        fix_instruction=(
                            review_decision
                            .fix_instruction
                        ),
                    )

                history.append(
                    IterationRecord(
                        iteration=iteration,
                        worker_prompt=(
                            worker_prompt
                        ),
                        worker_output=(
                            worker_output
                        ),
                        manager_review=(
                            manager_review
                        ),
                        approved=approved,
                        test_success=(
                            test_result.success
                        ),
                    )
                )

                latest_summary = summary
                latest_changes = file_changes
                latest_written_paths = (
                    written_paths
                )
                latest_test_result = (
                    test_result
                )
                latest_review = (
                    manager_review
                )

                if approved:
                    return PipelineResult(
                        goal=cleaned_goal,
                        summary=summary,
                        file_changes=(
                            file_changes
                        ),
                        written_paths=(
                            written_paths
                        ),
                        test_result=(
                            test_result
                        ),
                        manager_review=(
                            manager_review
                        ),
                        approved=True,
                        iterations=iteration,
                        history=history,
                    )

                worker_prompt = (
                    self._build_retry_prompt(
                        goal=grounded_goal,
                        manager_instruction=(
                            manager_instruction
                        ),
                        decision=(
                            review_decision
                        ),
                        test_result=(
                            test_result
                        ),
                        grounding_context=(
                            grounding_context
                        ),
                        execution_memory_context=(
                            self._execution_memory_context(
                                execution_memory
                            )
                        ),
                        iteration=(
                            iteration + 1
                        ),
                    )
                )

            except Exception as exc:
                error_message = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                latest_review = (
                    "DECISION: REJECTED\n\n"
                    "REASON:\n"
                    "The worker response could not "
                    "be processed.\n\n"
                    "FIX_INSTRUCTION:\n"
                    "Return valid JSON matching the "
                    "required schema with complete "
                    "file contents."
                )

                latest_test_result = (
                    StagingTestResult(
                        success=False,
                        command=[],
                        return_code=-1,
                        stdout="",
                        stderr=error_message,
                    )
                )

                if execution_memory is not None:
                    execution_memory.record(
                        iteration=iteration,
                        summary=(
                            "Worker response processing "
                            "failed before a valid staged "
                            "change set was produced."
                        ),
                        changed_paths=(),
                        test_success=False,
                        review_approved=False,
                        review_reason=(
                            "The worker response could "
                            "not be processed."
                        ),
                        fix_instruction=(
                            "Return valid JSON matching "
                            "the required schema with "
                            "complete file contents."
                        ),
                    )

                history.append(
                    IterationRecord(
                        iteration=iteration,
                        worker_prompt=(
                            worker_prompt
                        ),
                        worker_output=(
                            worker_output
                        ),
                        manager_review=(
                            latest_review
                        ),
                        approved=False,
                        test_success=False,
                    )
                )

                worker_prompt = (
                    self.prompt_builder
                    .build_retry_prompt(
                        goal=grounded_goal,
                        manager_instruction=(
                            manager_instruction
                        ),
                        rejection_reason=(
                            "The worker response "
                            "could not be processed."
                        ),
                        fix_instruction=(
                            "Return valid JSON "
                            "matching the required "
                            "schema with complete "
                            "file contents."
                        ),
                        test_output=(
                            self._append_execution_memory(
                                evidence=(
                                    self._render_retry_evidence(
                                        test_output=(
                                            error_message
                                        ),
                                        grounding_context=(
                                            grounding_context
                                        ),
                                    )
                                ),
                                execution_memory_context=(
                                    self._execution_memory_context(
                                        execution_memory
                                    )
                                ),
                            )
                        ),
                        iteration=(
                            iteration + 1
                        ),
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
        grounding_context: str,
        execution_memory_context: str = "",
        iteration: int = 1,
    ) -> str:
        evidence = (
            self._render_retry_evidence(
                test_output=(
                    test_result.combined_output
                    or (
                        "No staging diagnostics "
                        "were produced."
                    )
                ),
                grounding_context=(
                    grounding_context
                ),
            )
        )

        enriched_evidence = (
            self._append_execution_memory(
                evidence=evidence,
                execution_memory_context=(
                    execution_memory_context
                ),
            )
        )

        return (
            self.prompt_builder
            .build_retry_prompt(
                goal=goal,
                manager_instruction=(
                    manager_instruction
                ),
                rejection_reason=(
                    decision.reason
                ),
                fix_instruction=(
                    decision.fix_instruction
                ),
                test_output=enriched_evidence,
                iteration=iteration,
            )
        )

    @staticmethod
    def _execution_memory_context(
        memory: WorkflowExecutionMemory | None,
    ) -> str:
        if memory is None:
            return ""

        return (
            memory.build_context()
            .rendered_context
            .strip()
        )

    @staticmethod
    def _append_execution_memory(
        *,
        evidence: str,
        execution_memory_context: str,
    ) -> str:
        cleaned_evidence = evidence.strip()

        cleaned_memory = (
            execution_memory_context.strip()
        )

        if not cleaned_memory:
            return cleaned_evidence

        if not cleaned_evidence:
            return cleaned_memory

        return (
            f"{cleaned_evidence}\n\n"
            f"{cleaned_memory}"
        )

    def _build_planning_context(
        self,
        goal: str,
    ) -> str:
        if self.planning_service is None:
            return ""

        context = self.planning_service.build(
            goal
        )

        rendered = context.rendered_context.strip()

        if not rendered:
            raise RuntimeError(
                "Execution planning service "
                "returned empty context."
            )

        return rendered

    def _build_grounding_context(
        self,
        goal: str,
    ) -> str:
        if self.grounding_service is None:
            return ""

        grounding = (
            self.grounding_service.build(
                goal
            )
        )

        rendered = str(
            getattr(
                grounding,
                "rendered_context",
                "",
            )
        ).strip()

        if not rendered:
            raise RuntimeError(
                "Repository grounding service "
                "returned empty evidence."
            )

        return self._bounded_grounding(
            rendered
        )

    def _bounded_grounding(
        self,
        grounding_context: str,
    ) -> str:
        if (
            len(grounding_context)
            <= self.max_grounding_characters
        ):
            return grounding_context

        notice = (
            "\n\nGROUNDING CONTEXT TRUNCATED\n"
            "===========================\n"
            "The repository evidence exceeded "
            "the pipeline context limit. The "
            "verified beginning was retained."
        )

        available = (
            self.max_grounding_characters
            - len(notice)
        )

        return (
            grounding_context[
                :available
            ].rstrip()
            + notice
        )

    def _auto_grounding_service(
        self,
        *,
        enabled: bool,
    ) -> (
        RepositoryGroundingService
        | None
    ):
        if not enabled:
            return None

        staging_root = getattr(
            self.workspace_writer,
            "staging_root",
            None,
        )

        if staging_root is None:
            return None

        candidate_root = Path(
            staging_root
        ).resolve().parent

        if not (
            candidate_root / ".git"
        ).is_dir():
            return None

        return RepositoryGroundingService(
            project_root=candidate_root,
        )

    @staticmethod
    def _compose_grounded_goal(
        *,
        goal: str,
        planning_context: str,
        grounding_context: str,
    ) -> str:
        cleaned_planning = (
            planning_context.strip()
        )

        cleaned_grounding = (
            grounding_context.strip()
        )

        if (
            not cleaned_planning
            and not cleaned_grounding
        ):
            return goal

        sections = [
            (
                "ORIGINAL ARCHITECT GOAL\n"
                "=======================\n"
                f"{goal}"
            )
        ]

        if cleaned_planning:
            sections.append(
                cleaned_planning
            )

        if cleaned_grounding:
            sections.append(
                cleaned_grounding
            )

        return "\n\n".join(sections)

    @staticmethod
    def _build_review_input(
        *,
        worker_output: str,
        test_result: StagingTestResult,
        grounding_context: str,
    ) -> str:
        grounding_section = (
            grounding_context
            or (
                "No repository grounding was "
                "configured for this pipeline."
            )
        )

        return (
            "VERIFIED REPOSITORY EVIDENCE\n"
            "============================\n"
            f"{grounding_section}\n\n"
            "WORKER JSON OUTPUT\n"
            "==================\n"
            f"{worker_output}\n\n"
            "STAGING VALIDATION RESULT\n"
            "=========================\n"
            "Scope: temporary staged files "
            "generated by this worker attempt.\n"
            "Important: this result describes "
            "only the staging workspace. It must "
            "not be used to infer that the main "
            "repository has no source code or "
            "tests.\n"
            f"Success: {test_result.success}\n"
            "Return code: "
            f"{test_result.return_code}\n"
            "Output:\n"
            f"{test_result.combined_output or 'No output'}"
        )

    @staticmethod
    def _render_retry_evidence(
        *,
        test_output: str,
        grounding_context: str,
    ) -> str:
        repository_evidence = (
            grounding_context
            or (
                "Repository grounding was "
                "not configured."
            )
        )

        return (
            "CURRENT REPOSITORY EVIDENCE\n"
            "===========================\n"
            f"{repository_evidence}\n\n"
            "FAILED ATTEMPT DIAGNOSTICS\n"
            "==========================\n"
            f"{test_output}\n\n"
            "RETRY RULES\n"
            "===========\n"
            "- Preserve the original architect goal.\n"
            "- Use current repository evidence as truth.\n"
            "- Do not repeat a contradicted assumption.\n"
            "- Treat staging output only as staging evidence.\n"
            "- Correct only the failed attempt scope."
        )

    @staticmethod
    def _empty_test_result(
    ) -> StagingTestResult:
        return StagingTestResult(
            success=False,
            command=[],
            return_code=-1,
            stdout="",
            stderr=(
                "Pipeline did not produce "
                "a test result."
            ),
        )
