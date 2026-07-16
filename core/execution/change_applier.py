from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from core.execution.change_approval import (
    ChangeDiffGenerator,
    ChangeSet,
    HumanApprovalGate,
)
from core.execution.workspace import (
    SafeWorkspace,
    WorkspaceSecurityError,
)


@dataclass(slots=True, frozen=True)
class GitCommitResult:
    committed: bool
    commit_hash: str | None
    stdout: str
    stderr: str


@dataclass(slots=True, frozen=True)
class ApplyResult:
    fingerprint: str
    applied_files: tuple[str, ...]
    git_result: GitCommitResult | None


class ChangeApplyError(RuntimeError):
    """Raised when approved staged changes cannot be applied safely."""


class SafeChangeApplier:
    """
    Applies an approved staged change set to the real project.

    Safety guarantees:
    - Recomputes the current staged fingerprint before applying.
    - Requires approval for the exact current fingerprint.
    - Backs up every affected existing file.
    - Uses temporary files and atomic replacement.
    - Rolls back all applied files if any operation fails.
    - Git commit is optional and runs only after file application.
    """

    def __init__(
        self,
        workspace: SafeWorkspace,
        approval_gate: HumanApprovalGate,
        diff_generator: ChangeDiffGenerator | None = None,
        backup_directory: str = ".atlas_apply_backup",
        command_timeout_seconds: int = 120,
    ) -> None:
        if command_timeout_seconds < 1:
            raise ValueError(
                "command_timeout_seconds must be positive."
            )

        self.workspace = workspace
        self.approval_gate = approval_gate
        self.diff_generator = (
            diff_generator
            or ChangeDiffGenerator(workspace)
        )
        self.project_root = workspace.project_root
        self.command_timeout_seconds = command_timeout_seconds

        backup_path = Path(backup_directory)

        if backup_path.is_absolute():
            self.backup_root = backup_path.resolve()
        else:
            self.backup_root = (
                self.project_root / backup_path
            ).resolve()

        try:
            self.backup_root.relative_to(
                self.project_root
            )
        except ValueError as exc:
            raise WorkspaceSecurityError(
                "Backup directory must remain inside project root."
            ) from exc

    def apply(
        self,
        approved_change_set: ChangeSet,
        create_git_commit: bool = False,
        commit_message: str | None = None,
    ) -> ApplyResult:
        current_change_set = self.diff_generator.generate()

        if (
            current_change_set.fingerprint
            != approved_change_set.fingerprint
        ):
            raise PermissionError(
                "Staged files changed after approval. "
                "A new approval is required."
            )

        self.approval_gate.require_approved(
            current_change_set
        )

        if create_git_commit:
            cleaned_message = (
                commit_message.strip()
                if commit_message is not None
                else ""
            )

            if not cleaned_message:
                raise ValueError(
                    "commit_message is required when "
                    "create_git_commit is enabled."
                )

            self._require_git_repository()

        staged_files = (
            self.workspace.list_staged_files()
        )

        if not staged_files:
            raise ChangeApplyError(
                "No staged files are available to apply."
            )

        operation_backup_root = (
            self.backup_root
            / uuid4().hex
        )

        operation_backup_root.mkdir(
            parents=True,
            exist_ok=False,
        )

        original_existing_files: set[str] = set()
        applied_files: list[str] = []

        try:
            self._create_backups(
                staged_files=staged_files,
                operation_backup_root=(
                    operation_backup_root
                ),
                original_existing_files=(
                    original_existing_files
                ),
            )

            for relative_path in staged_files:
                self._apply_one_file(
                    relative_path
                )
                applied_files.append(
                    relative_path
                )

            git_result: GitCommitResult | None = None

            if create_git_commit:
                git_result = self._create_git_commit(
                    relative_paths=staged_files,
                    commit_message=(
                        commit_message.strip()
                    ),
                )

            self.workspace.discard()

            return ApplyResult(
                fingerprint=(
                    current_change_set.fingerprint
                ),
                applied_files=tuple(
                    applied_files
                ),
                git_result=git_result,
            )

        except Exception as exc:
            self._rollback(
                staged_files=staged_files,
                operation_backup_root=(
                    operation_backup_root
                ),
                original_existing_files=(
                    original_existing_files
                ),
            )

            if isinstance(
                exc,
                (
                    PermissionError,
                    ValueError,
                    ChangeApplyError,
                ),
            ):
                raise

            raise ChangeApplyError(
                "Applying staged changes failed and "
                "the project was rolled back: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        finally:
            if operation_backup_root.exists():
                shutil.rmtree(
                    operation_backup_root
                )

            self._remove_empty_backup_root()

    def _create_backups(
        self,
        staged_files: list[str],
        operation_backup_root: Path,
        original_existing_files: set[str],
    ) -> None:
        for relative_path in staged_files:
            project_path = self._resolve_project_path(
                relative_path
            )

            if not project_path.exists():
                continue

            if not project_path.is_file():
                raise ChangeApplyError(
                    f"Project path is not a file: "
                    f"{relative_path}"
                )

            original_existing_files.add(
                relative_path
            )

            backup_path = (
                operation_backup_root
                / relative_path
            )

            backup_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                project_path,
                backup_path,
            )

    def _apply_one_file(
        self,
        relative_path: str,
    ) -> None:
        staged_path = (
            self.workspace.staging_root
            / relative_path
        ).resolve()

        try:
            staged_path.relative_to(
                self.workspace.staging_root
            )
        except ValueError as exc:
            raise WorkspaceSecurityError(
                "Staged file escapes staging root."
            ) from exc

        if not staged_path.exists():
            raise FileNotFoundError(
                f"Staged file disappeared: {relative_path}"
            )

        if not staged_path.is_file():
            raise IsADirectoryError(
                f"Staged path is not a file: {relative_path}"
            )

        destination = self._resolve_project_path(
            relative_path
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = destination.with_name(
            destination.name
            + f".atlas-{uuid4().hex}.tmp"
        )

        shutil.copy2(
            staged_path,
            temporary_path,
        )

        temporary_path.replace(
            destination
        )

    def _rollback(
        self,
        staged_files: list[str],
        operation_backup_root: Path,
        original_existing_files: set[str],
    ) -> None:
        for relative_path in reversed(
            staged_files
        ):
            project_path = self._resolve_project_path(
                relative_path
            )

            if relative_path in original_existing_files:
                backup_path = (
                    operation_backup_root
                    / relative_path
                )

                if backup_path.exists():
                    project_path.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    shutil.copy2(
                        backup_path,
                        project_path,
                    )

                continue

            if project_path.exists():
                if project_path.is_file():
                    project_path.unlink()
                else:
                    shutil.rmtree(
                        project_path
                    )

    def _create_git_commit(
        self,
        relative_paths: list[str],
        commit_message: str,
    ) -> GitCommitResult:
        add_result = self._run_git(
            [
                "git",
                "add",
                "--",
                *relative_paths,
            ]
        )

        if add_result.returncode != 0:
            raise ChangeApplyError(
                "Git add failed: "
                f"{add_result.stderr.strip()}"
            )

        commit_result = self._run_git(
            [
                "git",
                "commit",
                "-m",
                commit_message,
            ]
        )

        if commit_result.returncode != 0:
            raise ChangeApplyError(
                "Git commit failed: "
                f"{commit_result.stderr.strip()}"
            )

        hash_result = self._run_git(
            [
                "git",
                "rev-parse",
                "HEAD",
            ]
        )

        if hash_result.returncode != 0:
            raise ChangeApplyError(
                "Git commit hash could not be read: "
                f"{hash_result.stderr.strip()}"
            )

        return GitCommitResult(
            committed=True,
            commit_hash=(
                hash_result.stdout.strip()
            ),
            stdout=commit_result.stdout,
            stderr=commit_result.stderr,
        )

    def _require_git_repository(
        self,
    ) -> None:
        result = self._run_git(
            [
                "git",
                "rev-parse",
                "--is-inside-work-tree",
            ]
        )

        if (
            result.returncode != 0
            or result.stdout.strip().lower()
            != "true"
        ):
            raise ChangeApplyError(
                "Project root is not a Git repository."
            )

    def _run_git(
        self,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=(
                    self.command_timeout_seconds
                ),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ChangeApplyError(
                "Git command timed out: "
                f"{' '.join(command)}"
            ) from exc
        except OSError as exc:
            raise ChangeApplyError(
                "Git command could not run: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _resolve_project_path(
        self,
        relative_path: str,
    ) -> Path:
        requested_path = Path(
            relative_path
        )

        if requested_path.is_absolute():
            raise WorkspaceSecurityError(
                "Only project-relative paths are allowed."
            )

        resolved_path = (
            self.project_root
            / requested_path
        ).resolve()

        try:
            resolved_path.relative_to(
                self.project_root
            )
        except ValueError as exc:
            raise WorkspaceSecurityError(
                "Apply path escapes project root."
            ) from exc

        return resolved_path

    def _remove_empty_backup_root(
        self,
    ) -> None:
        if not self.backup_root.exists():
            return

        try:
            next(
                self.backup_root.iterdir()
            )
        except StopIteration:
            self.backup_root.rmdir()
