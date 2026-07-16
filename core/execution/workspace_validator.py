from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.execution.workspace import (
    SafeWorkspace,
    WorkspaceSecurityError,
)


@dataclass(slots=True, frozen=True)
class ValidationCommandResult:
    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def passed(self) -> bool:
        return (
            self.return_code == 0
            and not self.timed_out
        )


@dataclass(slots=True, frozen=True)
class WorkspaceValidationResult:
    passed: bool
    validation_root: str
    syntax_result: ValidationCommandResult
    test_results: tuple[ValidationCommandResult, ...]
    summary: str


class WorkspaceValidationError(RuntimeError):
    """Raised when staged validation cannot run safely."""


class WorkspaceValidator:
    """
    Validates staged changes inside an isolated temporary project copy.

    Flow:
    - Copy approved project files to a validation directory.
    - Overlay staged files.
    - Run Python compile checks.
    - Run explicitly approved test commands.
    - Never modify the original project.
    """

    DEFAULT_EXCLUDED_DIRECTORIES = {
        ".git",
        ".atlas_data",
        ".atlas_staging",
        ".atlas_validation",
        ".atlas_apply_project",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }

    ALLOWED_COMMANDS = {
        "python",
        "python3",
        "pytest",
    }

    def __init__(
        self,
        workspace: SafeWorkspace,
        validation_directory: str = ".atlas_validation",
        command_timeout_seconds: int = 120,
    ) -> None:
        if command_timeout_seconds < 1:
            raise ValueError(
                "command_timeout_seconds must be positive."
            )

        self.workspace = workspace
        self.project_root = workspace.project_root

        validation_path = Path(validation_directory)

        if validation_path.is_absolute():
            self.validation_root = (
                validation_path.resolve()
            )
        else:
            self.validation_root = (
                self.project_root / validation_path
            ).resolve()

        try:
            self.validation_root.relative_to(
                self.project_root
            )
        except ValueError as exc:
            raise WorkspaceSecurityError(
                "Validation directory must remain "
                "inside the project root."
            ) from exc

        self.command_timeout_seconds = (
            command_timeout_seconds
        )

    def validate(
        self,
        test_commands: list[list[str]] | None = None,
    ) -> WorkspaceValidationResult:
        self._prepare_validation_copy()
        self._overlay_staged_files()

        syntax_result = self._run_command(
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                ".",
            ]
        )

        test_results: list[
            ValidationCommandResult
        ] = []

        if syntax_result.passed:
            for command in test_commands or []:
                self._validate_command(command)

                result = self._run_command(
                    command
                )

                test_results.append(result)

                if not result.passed:
                    break

        passed = (
            syntax_result.passed
            and all(
                result.passed
                for result in test_results
            )
        )

        summary = self._build_summary(
            syntax_result=syntax_result,
            test_results=test_results,
            passed=passed,
        )

        return WorkspaceValidationResult(
            passed=passed,
            validation_root=str(
                self.validation_root
            ),
            syntax_result=syntax_result,
            test_results=tuple(test_results),
            summary=summary,
        )

    def cleanup(self) -> None:
        if self.validation_root.exists():
            shutil.rmtree(
                self.validation_root
            )

    def _prepare_validation_copy(self) -> None:
        self.cleanup()

        self.validation_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        for source_path in self.project_root.rglob("*"):
            if source_path == self.validation_root:
                continue

            try:
                relative_path = source_path.relative_to(
                    self.project_root
                )
            except ValueError:
                continue

            if self._is_excluded(relative_path):
                continue

            destination = (
                self.validation_root
                / relative_path
            )

            if source_path.is_dir():
                destination.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                continue

            if source_path.is_file():
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.copy2(
                    source_path,
                    destination,
                )

    def _overlay_staged_files(self) -> None:
        for relative_path in (
            self.workspace.list_staged_files()
        ):
            staged_path = (
                self.workspace.staging_root
                / relative_path
            ).resolve()

            destination = (
                self.validation_root
                / relative_path
            ).resolve()

            try:
                destination.relative_to(
                    self.validation_root
                )
            except ValueError as exc:
                raise WorkspaceSecurityError(
                    "Staged file escapes validation root."
                ) from exc

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                staged_path,
                destination,
            )

    def _run_command(
        self,
        command: list[str],
    ) -> ValidationCommandResult:
        try:
            completed = subprocess.run(
                command,
                cwd=self.validation_root,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
                check=False,
            )

            return ValidationCommandResult(
                command=tuple(command),
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                timed_out=False,
            )

        except subprocess.TimeoutExpired as exc:
            return ValidationCommandResult(
                command=tuple(command),
                return_code=-1,
                stdout=self._safe_text(exc.stdout),
                stderr=self._safe_text(exc.stderr),
                timed_out=True,
            )

        except OSError as exc:
            return ValidationCommandResult(
                command=tuple(command),
                return_code=-1,
                stdout="",
                stderr=(
                    f"{type(exc).__name__}: {exc}"
                ),
                timed_out=False,
            )

    def _validate_command(
        self,
        command: list[str],
    ) -> None:
        if not command:
            raise WorkspaceValidationError(
                "Validation command cannot be empty."
            )

        blocked_arguments = {
            "-c",
            "--eval",
        }

        if any(
            argument in blocked_arguments
            for argument in command[1:]
        ):
            raise WorkspaceValidationError(
                "Inline code execution is blocked."
            )

        executable_name = Path(
            command[0]
        ).name.lower()

        if executable_name.endswith(".exe"):
            executable_name = (
                executable_name[:-4]
            )

        allowed_python_paths = {
            Path(sys.executable).resolve(),
        }

        supplied_path = Path(command[0])

        if supplied_path.is_absolute():
            if (
                supplied_path.resolve()
                not in allowed_python_paths
            ):
                raise WorkspaceValidationError(
                    "Absolute executable path is not approved."
                )

            return

        if executable_name not in self.ALLOWED_COMMANDS:
            raise WorkspaceValidationError(
                f"Validation command is not approved: "
                f"{command[0]}"
            )

    def _is_excluded(
        self,
        relative_path: Path,
    ) -> bool:
        return any(
            part in self.DEFAULT_EXCLUDED_DIRECTORIES
            for part in relative_path.parts
        )

    @staticmethod
    def _safe_text(
        value: str | bytes | None,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, bytes):
            return value.decode(
                "utf-8",
                errors="replace",
            )

        return value

    @staticmethod
    def _build_summary(
        syntax_result: ValidationCommandResult,
        test_results: list[
            ValidationCommandResult
        ],
        passed: bool,
    ) -> str:
        lines = [
            (
                "Workspace validation passed."
                if passed
                else "Workspace validation failed."
            ),
            (
                "Syntax check: PASSED"
                if syntax_result.passed
                else "Syntax check: FAILED"
            ),
        ]

        for index, result in enumerate(
            test_results,
            start=1,
        ):
            lines.append(
                f"Test command {index}: "
                f"{'PASSED' if result.passed else 'FAILED'} "
                f"({' '.join(result.command)})"
            )

        if not test_results:
            lines.append(
                "Test commands: none configured."
            )

        return "\n".join(lines)
