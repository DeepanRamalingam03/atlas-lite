from __future__ import annotations

import subprocess
from pathlib import Path

from git_tools.models import GitCommandResult, GitPublishResult


class GitEngine:
    """
    Safe Git command wrapper for Atlas Lite.

    Responsibilities:
    - Inspect repository status.
    - Stage selected files.
    - Commit staged changes.
    - Push commits.
    - Return structured command results.
    """

    def __init__(
        self,
        repository_root: str | Path,
        timeout_seconds: int = 120,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        self.repository_root = Path(repository_root).resolve()
        self.timeout_seconds = timeout_seconds

        if not self.repository_root.exists():
            raise FileNotFoundError(
                f"Repository root does not exist: "
                f"{self.repository_root}"
            )

        if not self.repository_root.is_dir():
            raise NotADirectoryError(
                f"Repository root is not a directory: "
                f"{self.repository_root}"
            )

        if not (self.repository_root / ".git").is_dir():
            raise ValueError(
                f"Not a Git repository: {self.repository_root}"
            )

    def status(self) -> GitCommandResult:
        return self._run(
            [
                "git",
                "status",
                "--porcelain",
            ]
        )

    def changed_files(self) -> list[str]:
        result = self.status()

        if not result.success:
            raise RuntimeError(
                "Unable to read Git status:\n"
                f"{result.combined_output}"
            )

        files: list[str] = []

        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue

            path = line[3:].strip()

            if " -> " in path:
                path = path.split(" -> ", maxsplit=1)[1]

            if path:
                files.append(path)

        return files

    def add(self, paths: list[str]) -> GitCommandResult:
        cleaned_paths = [
            path.strip()
            for path in paths
            if path.strip()
        ]

        if not cleaned_paths:
            raise ValueError(
                "At least one file path is required for git add."
            )

        self._validate_paths(cleaned_paths)

        return self._run(
            [
                "git",
                "add",
                "--",
                *cleaned_paths,
            ]
        )

    def commit(self, message: str) -> GitCommandResult:
        cleaned_message = message.strip()

        if not cleaned_message:
            raise ValueError(
                "Git commit message cannot be empty."
            )

        return self._run(
            [
                "git",
                "commit",
                "-m",
                cleaned_message,
            ]
        )

    def push(
        self,
        remote: str = "origin",
        branch: str = "main",
    ) -> GitCommandResult:
        cleaned_remote = remote.strip()
        cleaned_branch = branch.strip()

        if not cleaned_remote:
            raise ValueError("Git remote cannot be empty.")

        if not cleaned_branch:
            raise ValueError("Git branch cannot be empty.")

        return self._run(
            [
                "git",
                "push",
                cleaned_remote,
                cleaned_branch,
            ]
        )

    def publish(
        self,
        paths: list[str],
        commit_message: str,
        remote: str = "origin",
        branch: str = "main",
        push: bool = True,
    ) -> GitPublishResult:
        status_result = self.status()

        if not status_result.success:
            return GitPublishResult(
                success=False,
                status_result=status_result,
                error=(
                    "Git status failed: "
                    f"{status_result.combined_output}"
                ),
            )

        changed_files = self.changed_files()

        if not changed_files:
            return GitPublishResult(
                success=True,
                status_result=status_result,
                changed_files=[],
                committed=False,
                pushed=False,
            )

        add_result = self.add(paths)

        if not add_result.success:
            return GitPublishResult(
                success=False,
                status_result=status_result,
                add_result=add_result,
                changed_files=changed_files,
                error=(
                    "Git add failed: "
                    f"{add_result.combined_output}"
                ),
            )

        commit_result = self.commit(commit_message)

        if not commit_result.success:
            return GitPublishResult(
                success=False,
                status_result=status_result,
                add_result=add_result,
                commit_result=commit_result,
                changed_files=changed_files,
                error=(
                    "Git commit failed: "
                    f"{commit_result.combined_output}"
                ),
            )

        if not push:
            return GitPublishResult(
                success=True,
                status_result=status_result,
                add_result=add_result,
                commit_result=commit_result,
                changed_files=changed_files,
                committed=True,
                pushed=False,
            )

        push_result = self.push(
            remote=remote,
            branch=branch,
        )

        if not push_result.success:
            return GitPublishResult(
                success=False,
                status_result=status_result,
                add_result=add_result,
                commit_result=commit_result,
                push_result=push_result,
                changed_files=changed_files,
                committed=True,
                pushed=False,
                error=(
                    "Git push failed after commit: "
                    f"{push_result.combined_output}"
                ),
            )

        return GitPublishResult(
            success=True,
            status_result=status_result,
            add_result=add_result,
            commit_result=commit_result,
            push_result=push_result,
            changed_files=changed_files,
            committed=True,
            pushed=True,
        )

    def _run(
        self,
        command: list[str],
    ) -> GitCommandResult:
        try:
            completed = subprocess.run(
                command,
                cwd=self.repository_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )

            return GitCommandResult(
                success=completed.returncode == 0,
                command=command,
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode(
                    "utf-8",
                    errors="replace",
                )

            if isinstance(stderr, bytes):
                stderr = stderr.decode(
                    "utf-8",
                    errors="replace",
                )

            return GitCommandResult(
                success=False,
                command=command,
                return_code=-1,
                stdout=stdout,
                stderr=(
                    stderr
                    or (
                        "Git command timed out after "
                        f"{self.timeout_seconds} seconds."
                    )
                ),
            )

    @staticmethod
    def _validate_paths(paths: list[str]) -> None:
        protected = {
            ".env",
            ".git",
            "venv",
            ".atlas_staging",
            ".atlas_backups",
        }

        for raw_path in paths:
            path = Path(raw_path)

            if path.is_absolute():
                raise ValueError(
                    f"Absolute Git path is not allowed: {raw_path}"
                )

            if ".." in path.parts:
                raise ValueError(
                    f"Parent traversal is not allowed: {raw_path}"
                )

            if path.parts and path.parts[0] in protected:
                raise PermissionError(
                    f"Protected path cannot be staged: {raw_path}"
                )
