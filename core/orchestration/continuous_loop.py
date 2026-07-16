from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol

from core.orchestration.autonomy_policy import (
    AutonomyAction,
    AutonomyDecision,
    AutonomyPolicy,
    AutonomyRequest,
)
from core.orchestration.models import (
    WorkflowRecord,
    WorkflowStatus,
)
from core.orchestration.state_store import WorkflowStateStore


class DevelopmentPipeline(Protocol):
    def execute(self, goal: str) -> Any:
        """Execute manager, worker, staging, validation, and review."""


class DevelopmentReleaseCoordinator(Protocol):
    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan: Any | None = None,
    ) -> Any:
        """Apply, commit, and optionally push staged changes."""


@dataclass(slots=True, frozen=True)
class ContinuousRunResult:
    workflow: WorkflowRecord
    pipeline_result: Any | None
    release_result: Any | None
    autonomy_decision: AutonomyDecision | None
    completed: bool
    waiting_for_human: bool
    error: str | None


class ContinuousOrchestrator:
    """
    Connects the existing Atlas development modules into one runtime cycle.

    Existing module flow:
    - AtlasPipeline performs Manager -> Worker -> Staging -> Validation
      -> Manager Review.
    - AutonomyPolicy decides whether the proposed operation can continue.
    - ReleaseCoordinator performs transactional apply, Git commit, and push.
    - WorkflowStateStore persists every important lifecycle transition.
    """

    def __init__(
        self,
        pipeline: DevelopmentPipeline,
        release_coordinator: DevelopmentReleaseCoordinator,
        workflow_store: WorkflowStateStore | None = None,
        autonomy_policy: AutonomyPolicy | None = None,
        remote: str = "origin",
        branch: str = "main",
        push: bool = True,
    ) -> None:
        cleaned_remote = remote.strip()
        cleaned_branch = branch.strip()

        if not cleaned_remote:
            raise ValueError("remote cannot be empty.")

        if not cleaned_branch:
            raise ValueError("branch cannot be empty.")

        self.pipeline = pipeline
        self.release_coordinator = release_coordinator
        self.workflow_store = (
            workflow_store or WorkflowStateStore()
        )
        self.autonomy_policy = (
            autonomy_policy or AutonomyPolicy()
        )
        self.remote = cleaned_remote
        self.branch = cleaned_branch
        self.push = push

    def run_goal(
        self,
        user_id: int,
        goal: str,
        *,
        workflow_id: str | None = None,
        commit_message: str | None = None,
    ) -> ContinuousRunResult:
        cleaned_goal = goal.strip()

        if user_id < 1:
            raise ValueError("user_id must be positive.")

        if not cleaned_goal:
            raise ValueError("goal cannot be empty.")

        workflow = self.workflow_store.create(
            user_id=user_id,
            goal=cleaned_goal,
            workflow_id=workflow_id,
        )

        pipeline_result: Any | None = None
        release_result: Any | None = None
        autonomy_decision: AutonomyDecision | None = None

        try:
            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.PLANNING,
                summary="Preparing autonomous development workflow.",
                clear_error=True,
            )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.EXECUTING,
                summary=(
                    "Running manager, worker, staging, validation, "
                    "and review pipeline."
                ),
            )

            pipeline_result = self.pipeline.execute(
                cleaned_goal
            )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.VALIDATING,
                summary="Pipeline validation completed.",
            )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.REVIEWING,
                summary="Manager review completed.",
            )

            if not bool(
                getattr(pipeline_result, "approved", False)
            ):
                error = self._pipeline_failure_message(
                    pipeline_result
                )

                workflow = self.workflow_store.update(
                    workflow.workflow_id,
                    status=WorkflowStatus.FAILED,
                    summary="Pipeline did not receive manager approval.",
                    error=error,
                )

                return ContinuousRunResult(
                    workflow=workflow,
                    pipeline_result=pipeline_result,
                    release_result=None,
                    autonomy_decision=None,
                    completed=False,
                    waiting_for_human=False,
                    error=error,
                )

            proposed_paths = self._extract_proposed_paths(
                pipeline_result
            )

            autonomy_decision = (
                self.autonomy_policy.evaluate(
                    AutonomyRequest(
                        action=AutonomyAction.APPLY_CHANGE,
                        paths=tuple(proposed_paths),
                        branch=self.branch,
                    )
                )
            )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.WAITING_APPROVAL,
                approval_fingerprint=(
                    self._approval_reference(
                        workflow.workflow_id,
                        proposed_paths,
                    )
                ),
                summary=autonomy_decision.message,
            )

            if autonomy_decision.blocked:
                return ContinuousRunResult(
                    workflow=workflow,
                    pipeline_result=pipeline_result,
                    release_result=None,
                    autonomy_decision=autonomy_decision,
                    completed=False,
                    waiting_for_human=True,
                    error=None,
                )

            if self.push:
                push_decision = (
                    self.autonomy_policy.evaluate(
                        AutonomyRequest(
                            action=AutonomyAction.GIT_PUSH,
                            paths=tuple(proposed_paths),
                            branch=self.branch,
                            metadata={
                                "force_push": False,
                            },
                        )
                    )
                )

                if push_decision.blocked:
                    workflow = self.workflow_store.update(
                        workflow.workflow_id,
                        summary=push_decision.message,
                    )

                    return ContinuousRunResult(
                        workflow=workflow,
                        pipeline_result=pipeline_result,
                        release_result=None,
                        autonomy_decision=push_decision,
                        completed=False,
                        waiting_for_human=True,
                        error=None,
                    )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.APPROVED,
                summary=(
                    "Autonomy policy approved routine development work."
                ),
            )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.APPLYING,
                summary=(
                    "Applying staged changes and publishing approved work."
                ),
            )

            resolved_commit_message = (
                commit_message.strip()
                if commit_message is not None
                and commit_message.strip()
                else self._default_commit_message(
                    cleaned_goal
                )
            )

            release_result = (
                self.release_coordinator.release(
                    commit_message=resolved_commit_message,
                    push=self.push,
                    remote=self.remote,
                    branch=self.branch,
                )
            )

            if not bool(
                getattr(release_result, "success", False)
            ):
                error = (
                    getattr(release_result, "error", None)
                    or "Release coordinator failed."
                )

                workflow = self.workflow_store.update(
                    workflow.workflow_id,
                    status=WorkflowStatus.FAILED,
                    summary="Autonomous release failed.",
                    error=str(error),
                )

                return ContinuousRunResult(
                    workflow=workflow,
                    pipeline_result=pipeline_result,
                    release_result=release_result,
                    autonomy_decision=autonomy_decision,
                    completed=False,
                    waiting_for_human=False,
                    error=str(error),
                )

            workflow = self.workflow_store.update(
                workflow.workflow_id,
                status=WorkflowStatus.COMPLETED,
                summary=(
                    "Autonomous development workflow completed."
                ),
                clear_current_task=True,
                clear_approval=True,
                clear_error=True,
            )

            return ContinuousRunResult(
                workflow=workflow,
                pipeline_result=pipeline_result,
                release_result=release_result,
                autonomy_decision=autonomy_decision,
                completed=True,
                waiting_for_human=False,
                error=None,
            )

        except Exception as exc:
            error = (
                f"{type(exc).__name__}: {exc}"
            )

            workflow = self._mark_failed_when_possible(
                workflow.workflow_id,
                error,
            )

            return ContinuousRunResult(
                workflow=workflow,
                pipeline_result=pipeline_result,
                release_result=release_result,
                autonomy_decision=autonomy_decision,
                completed=False,
                waiting_for_human=(
                    workflow.status
                    == WorkflowStatus.WAITING_APPROVAL
                ),
                error=error,
            )

    def progress(
        self,
        workflow_id: str,
    ) -> WorkflowRecord:
        return self.workflow_store.require(
            workflow_id
        )

    def _mark_failed_when_possible(
        self,
        workflow_id: str,
        error: str,
    ) -> WorkflowRecord:
        current = self.workflow_store.require(
            workflow_id
        )

        if current.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.STOPPED,
            WorkflowStatus.WAITING_APPROVAL,
        }:
            return self.workflow_store.update(
                workflow_id,
                summary="Workflow stopped after an execution error.",
                error=error,
            )

        return self.workflow_store.update(
            workflow_id,
            status=WorkflowStatus.FAILED,
            summary="Workflow failed during autonomous execution.",
            error=error,
        )

    @staticmethod
    def _extract_proposed_paths(
        pipeline_result: Any,
    ) -> list[str]:
        raw_changes = getattr(
            pipeline_result,
            "file_changes",
            None,
        )

        if raw_changes is None:
            raise RuntimeError(
                "Pipeline result does not contain file_changes."
            )

        paths: list[str] = []

        for change in raw_changes:
            raw_path = getattr(change, "path", None)

            if raw_path is None:
                raise RuntimeError(
                    "Pipeline file change does not contain a path."
                )

            cleaned_path = str(raw_path).strip().replace(
                "\\",
                "/",
            )

            if not cleaned_path:
                raise RuntimeError(
                    "Pipeline proposed an empty file path."
                )

            normalized = PurePosixPath(
                cleaned_path
            )

            if (
                normalized.is_absolute()
                or ".." in normalized.parts
            ):
                raise RuntimeError(
                    "Pipeline proposed an unsafe file path: "
                    f"{cleaned_path}"
                )

            paths.append(
                normalized.as_posix()
            )

        if not paths:
            raise RuntimeError(
                "Pipeline produced no file changes."
            )

        return sorted(set(paths))

    @staticmethod
    def _pipeline_failure_message(
        pipeline_result: Any,
    ) -> str:
        review = str(
            getattr(
                pipeline_result,
                "manager_review",
                "",
            )
        ).strip()

        test_result = getattr(
            pipeline_result,
            "test_result",
            None,
        )

        test_output = ""

        if test_result is not None:
            test_output = str(
                getattr(
                    test_result,
                    "combined_output",
                    "",
                )
            ).strip()

        details = [
            value
            for value in (
                review,
                test_output,
            )
            if value
        ]

        if not details:
            return (
                "Pipeline finished without manager approval."
            )

        return "\n\n".join(details)

    @staticmethod
    def _default_commit_message(
        goal: str,
    ) -> str:
        single_line = " ".join(
            goal.split()
        )

        if len(single_line) > 72:
            single_line = (
                single_line[:69].rstrip()
                + "..."
            )

        return f"Atlas - {single_line}"

    @staticmethod
    def _approval_reference(
        workflow_id: str,
        paths: list[str],
    ) -> str:
        path_summary = "|".join(paths)

        return (
            f"autonomy:{workflow_id}:"
            f"{abs(hash(path_summary))}"
        )
