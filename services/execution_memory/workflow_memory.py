from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


@dataclass(slots=True, frozen=True)
class ExecutionAttemptMemory:
    """
    Safe, bounded summary of one pipeline iteration.

    Raw prompts, complete model responses, source-code contents,
    credentials, and environment values are deliberately excluded.
    """

    iteration: int
    summary: str
    changed_paths: tuple[str, ...]
    test_success: bool
    review_approved: bool
    review_reason: str
    fix_instruction: str
    failure_signature: str

    def __post_init__(self) -> None:
        if self.iteration < 1:
            raise ValueError(
                "iteration must be at least 1."
            )

        if not self.failure_signature.strip():
            raise ValueError(
                "failure_signature cannot be empty."
            )


@dataclass(slots=True, frozen=True)
class ExecutionMemoryContext:
    attempt_count: int
    repeated_failure_count: int
    rendered_context: str


class WorkflowExecutionMemory:
    """
    In-memory, workflow-scoped retry evidence.

    A new instance is expected for each AtlasPipeline.execute() call.
    Nothing is persisted to disk, Git, or long-term project memory.

    The memory is intentionally bounded so retries do not grow prompts
    without limit.
    """

    SECRET_PATTERNS = (
        re.compile(
            r"(?i)\b(api[_-]?key|token|password|secret|authorization)"
            r"\s*[:=]\s*[^\s,;]+"
        ),
        re.compile(
            r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"
        ),
        re.compile(
            r"\bsk-[A-Za-z0-9_-]{8,}\b"
        ),
    )

    def __init__(
        self,
        *,
        max_attempts: int = 6,
        max_paths_per_attempt: int = 30,
        max_field_characters: int = 1_500,
        max_context_characters: int = 10_000,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(
                "max_attempts must be at least 1."
            )

        if max_attempts > 50:
            raise ValueError(
                "max_attempts cannot exceed 50."
            )

        if max_paths_per_attempt < 1:
            raise ValueError(
                "max_paths_per_attempt must be at least 1."
            )

        if max_field_characters < 100:
            raise ValueError(
                "max_field_characters must be at least 100."
            )

        if max_context_characters < 1_000:
            raise ValueError(
                "max_context_characters must be at least 1000."
            )

        self.max_attempts = max_attempts
        self.max_paths_per_attempt = (
            max_paths_per_attempt
        )
        self.max_field_characters = (
            max_field_characters
        )
        self.max_context_characters = (
            max_context_characters
        )

        self._attempts: list[
            ExecutionAttemptMemory
        ] = []

    def record(
        self,
        *,
        iteration: int,
        summary: str,
        changed_paths: Iterable[
            str | PurePosixPath
        ],
        test_success: bool,
        review_approved: bool,
        review_reason: str,
        fix_instruction: str,
    ) -> ExecutionAttemptMemory:
        if iteration < 1:
            raise ValueError(
                "iteration must be at least 1."
            )

        if any(
            attempt.iteration == iteration
            for attempt in self._attempts
        ):
            raise ValueError(
                "An execution-memory record already "
                f"exists for iteration {iteration}."
            )

        cleaned_summary = self._clean_field(
            summary,
            fallback="No worker summary was provided.",
        )

        cleaned_reason = self._clean_field(
            review_reason,
            fallback="No manager review reason was provided.",
        )

        cleaned_fix = self._clean_field(
            fix_instruction,
            fallback="No fix instruction was provided.",
        )

        normalized_paths = (
            self._normalize_paths(
                changed_paths
            )
        )

        signature = self._failure_signature(
            test_success=test_success,
            review_approved=review_approved,
            review_reason=cleaned_reason,
            fix_instruction=cleaned_fix,
        )

        attempt = ExecutionAttemptMemory(
            iteration=iteration,
            summary=cleaned_summary,
            changed_paths=normalized_paths,
            test_success=bool(test_success),
            review_approved=bool(
                review_approved
            ),
            review_reason=cleaned_reason,
            fix_instruction=cleaned_fix,
            failure_signature=signature,
        )

        self._attempts.append(attempt)
        self._attempts.sort(
            key=lambda item: item.iteration
        )

        if len(self._attempts) > self.max_attempts:
            self._attempts = self._attempts[
                -self.max_attempts:
            ]

        return attempt

    def list_attempts(
        self,
    ) -> tuple[ExecutionAttemptMemory, ...]:
        return tuple(self._attempts)

    def clear(self) -> None:
        self._attempts.clear()

    def build_context(
        self,
    ) -> ExecutionMemoryContext:
        attempts = self.list_attempts()

        if not attempts:
            return ExecutionMemoryContext(
                attempt_count=0,
                repeated_failure_count=0,
                rendered_context="",
            )

        repeated_failure_count = (
            self._repeated_failure_count(
                attempts
            )
        )

        rendered = self._render(
            attempts=attempts,
            repeated_failure_count=(
                repeated_failure_count
            ),
        )

        return ExecutionMemoryContext(
            attempt_count=len(attempts),
            repeated_failure_count=(
                repeated_failure_count
            ),
            rendered_context=self._bound_context(
                rendered
            ),
        )

    def latest(
        self,
    ) -> ExecutionAttemptMemory | None:
        if not self._attempts:
            return None

        return self._attempts[-1]

    @classmethod
    def _failure_signature(
        cls,
        *,
        test_success: bool,
        review_approved: bool,
        review_reason: str,
        fix_instruction: str,
    ) -> str:
        material = "\n".join(
            [
                f"test_success={test_success}",
                (
                    "review_approved="
                    f"{review_approved}"
                ),
                cls._canonicalize(
                    review_reason
                ),
                cls._canonicalize(
                    fix_instruction
                ),
            ]
        )

        digest = hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()

        return digest[:16]

    @classmethod
    def _canonicalize(
        cls,
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip().lower()

    def _clean_field(
        self,
        value: str,
        *,
        fallback: str,
    ) -> str:
        cleaned = re.sub(
            r"\s+",
            " ",
            str(value or ""),
        ).strip()

        if not cleaned:
            cleaned = fallback

        cleaned = self._redact(cleaned)

        if len(cleaned) > self.max_field_characters:
            suffix = " [truncated]"

            available = (
                self.max_field_characters
                - len(suffix)
            )

            cleaned = (
                cleaned[:available].rstrip()
                + suffix
            )

        return cleaned

    def _normalize_paths(
        self,
        paths: Iterable[
            str | PurePosixPath
        ],
    ) -> tuple[str, ...]:
        normalized: list[str] = []

        for value in paths:
            raw = str(value).strip()

            if not raw:
                continue

            candidate = raw.replace(
                "\\",
                "/",
            )

            path = PurePosixPath(candidate)

            if path.is_absolute():
                continue

            if ".." in path.parts:
                continue

            cleaned = str(path)

            if cleaned in {
                "",
                ".",
            }:
                continue

            if cleaned not in normalized:
                normalized.append(cleaned)

            if (
                len(normalized)
                >= self.max_paths_per_attempt
            ):
                break

        return tuple(normalized)

    @classmethod
    def _redact(
        cls,
        value: str,
    ) -> str:
        redacted = value

        for pattern in cls.SECRET_PATTERNS:
            redacted = pattern.sub(
                "[REDACTED]",
                redacted,
            )

        return redacted

    @staticmethod
    def _repeated_failure_count(
        attempts: tuple[
            ExecutionAttemptMemory,
            ...,
        ],
    ) -> int:
        failed_signatures = [
            attempt.failure_signature
            for attempt in attempts
            if (
                not attempt.test_success
                or not attempt.review_approved
            )
        ]

        if not failed_signatures:
            return 0

        latest_signature = (
            failed_signatures[-1]
        )

        return sum(
            signature == latest_signature
            for signature in failed_signatures
        )

    @staticmethod
    def _render(
        *,
        attempts: tuple[
            ExecutionAttemptMemory,
            ...,
        ],
        repeated_failure_count: int,
    ) -> str:
        lines = [
            "WORKFLOW EXECUTION MEMORY",
            "=========================",
            (
                "Recorded attempts: "
                f"{len(attempts)}"
            ),
            (
                "Current repeated failure count: "
                f"{repeated_failure_count}"
            ),
            "",
            "MEMORY RULES",
            "============",
            "- Use this only as retry evidence for the current workflow.",
            "- Do not assume a previous change is correct merely because "
            "it was attempted.",
            "- Repository grounding remains the source of truth.",
            "- Do not repeat the same rejected implementation unchanged.",
            "- Preserve useful verified work when preparing the next fix.",
            "- Resolve the latest validation or review failure directly.",
            "- Do not recreate unrelated files.",
        ]

        if repeated_failure_count >= 2:
            lines.extend(
                [
                    "",
                    "REPEATED FAILURE WARNING",
                    "========================",
                    (
                        "The latest failure signature has occurred "
                        f"{repeated_failure_count} times."
                    ),
                    (
                        "Do not retry the same approach without a "
                        "materially different correction."
                    ),
                ]
            )

        for attempt in attempts:
            paths = (
                ", ".join(
                    attempt.changed_paths
                )
                if attempt.changed_paths
                else "none"
            )

            lines.extend(
                [
                    "",
                    (
                        f"ATTEMPT {attempt.iteration}"
                    ),
                    (
                        "-" * (
                            len(
                                str(
                                    attempt.iteration
                                )
                            )
                            + 8
                        )
                    ),
                    (
                        "Summary: "
                        f"{attempt.summary}"
                    ),
                    (
                        "Changed paths: "
                        f"{paths}"
                    ),
                    (
                        "Tests passed: "
                        f"{attempt.test_success}"
                    ),
                    (
                        "Manager approved: "
                        f"{attempt.review_approved}"
                    ),
                    (
                        "Review reason: "
                        f"{attempt.review_reason}"
                    ),
                    (
                        "Required correction: "
                        f"{attempt.fix_instruction}"
                    ),
                    (
                        "Failure signature: "
                        f"{attempt.failure_signature}"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "NEXT ITERATION EXPECTATION",
                "==========================",
                (
                    "Build on verified progress, correct the latest "
                    "failure, and return a materially improved staged "
                    "result rather than repeating the previous output."
                ),
            ]
        )

        return "\n".join(lines)

    def _bound_context(
        self,
        rendered: str,
    ) -> str:
        if (
            len(rendered)
            <= self.max_context_characters
        ):
            return rendered

        notice = (
            "\n\nEXECUTION MEMORY TRUNCATED\n"
            "==========================\n"
            "The newest bounded workflow evidence was retained."
        )

        available = (
            self.max_context_characters
            - len(notice)
        )

        return (
            rendered[:available].rstrip()
            + notice
        )


__all__ = [
    "ExecutionAttemptMemory",
    "ExecutionMemoryContext",
    "WorkflowExecutionMemory",
]
