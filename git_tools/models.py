from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GitCommandResult:
    success: bool
    command: list[str]
    return_code: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return "\n".join(
            value.strip()
            for value in (self.stdout, self.stderr)
            if value.strip()
        )


@dataclass(slots=True)
class GitPublishResult:
    success: bool
    status_result: GitCommandResult
    add_result: GitCommandResult | None = None
    commit_result: GitCommandResult | None = None
    push_result: GitCommandResult | None = None
    committed: bool = False
    pushed: bool = False
    error: str | None = None
    changed_files: list[str] = field(default_factory=list)
