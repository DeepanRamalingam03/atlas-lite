from __future__ import annotations

from pathlib import Path

from apply.engine import TransactionalApplyEngine
from git_tools.engine import GitEngine
from release.models import ReleaseResult
from workspace.diff_engine import DiffPlan, WorkspaceDiffEngine


class ReleaseCoordinator:
    """
    Coordinates the approved Atlas release flow.

    Flow:
    1. Build or receive a workspace diff plan.
    2. Apply actionable staged files transactionally.
    3. Commit only applied files.
    4. Optionally push the commit.
    """

    def __init__(
        self,
        project_root: str | Path,
        staging_root: str | Path,
        git_engine: GitEngine,
        apply_engine: TransactionalApplyEngine,
        diff_engine: WorkspaceDiffEngine,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.staging_root = Path(staging_root).resolve()
        self.git_engine = git_engine
        self.apply_engine = apply_engine
        self.diff_engine = diff_engine

    def preview(self) -> DiffPlan:
        """Build and return the current staging diff plan."""
        return self.diff_engine.build_plan()

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan: DiffPlan | None = None,
    ) -> ReleaseResult:
        cleaned_message = commit_message.strip()

        if not cleaned_message:
            raise ValueError("Commit message cannot be empty.")

        active_plan = (
            diff_plan
            if diff_plan is not None
            else self.preview()
        )

        if not active_plan.has_changes:
            return ReleaseResult(
                success=True,
                diff_plan=active_plan,
            )

        apply_result = self.apply_engine.apply(active_plan)

        if not apply_result.success:
            return ReleaseResult(
                success=False,
                diff_plan=active_plan,
                apply_result=apply_result,
                error=(
                    apply_result.error
                    or "Transactional apply operation failed."
                ),
            )

        applied_relative_paths = [
            path.resolve()
            .relative_to(self.project_root)
            .as_posix()
            for path in apply_result.applied_paths
        ]

        git_result = self.git_engine.publish(
            paths=applied_relative_paths,
            commit_message=cleaned_message,
            remote=remote,
            branch=branch,
            push=push,
        )

        if not git_result.success:
            return ReleaseResult(
                success=False,
                diff_plan=active_plan,
                apply_result=apply_result,
                git_result=git_result,
                error=(
                    git_result.error
                    or "Git publish operation failed."
                ),
            )

        return ReleaseResult(
            success=True,
            diff_plan=active_plan,
            apply_result=apply_result,
            git_result=git_result,
        )
