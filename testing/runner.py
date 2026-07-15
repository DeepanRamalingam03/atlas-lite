from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class StagingTestResult:
    success: bool
    command: list[str]
    return_code: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        """Return stdout and stderr as one diagnostic string."""
        return "\n".join(
            part.strip()
            for part in (self.stdout, self.stderr)
            if part.strip()
        )


class StagingTestRunner:
    """
    Validates Python files inside the isolated Atlas staging workspace.

    Generated application code is not executed.
    Only Python syntax compilation is performed.
    """

    def __init__(
        self,
        staging_root: str | Path = ".atlas_staging",
        timeout_seconds: int = 60,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self.staging_root = Path(staging_root).resolve()
        self.timeout_seconds = timeout_seconds

    def run_compile_check(self) -> StagingTestResult:
        """Compile every Python file inside the staging workspace."""

        if not self.staging_root.exists():
            raise FileNotFoundError(
                f"Staging workspace does not exist: {self.staging_root}"
            )

        python_files = list(self.staging_root.rglob("*.py"))

        if not python_files:
            return StagingTestResult(
                success=True,
                command=[],
                return_code=0,
                stdout="No Python files found. Compile check skipped.",
                stderr="",
            )

        command = [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            str(self.staging_root),
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")

            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")

            return StagingTestResult(
                success=False,
                command=command,
                return_code=-1,
                stdout=stdout,
                stderr=(
                    stderr
                    or (
                        "Compile check timed out after "
                        f"{self.timeout_seconds} seconds."
                    )
                ),
            )

        return StagingTestResult(
            success=completed.returncode == 0,
            command=command,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
