from __future__ import annotations

import logging
from dataclasses import dataclass

from workers.base_worker import BaseWorker


logger = logging.getLogger(__name__)


@dataclass(
    slots=True,
    frozen=True,
)
class WorkerAttempt:
    provider: str
    successful: bool
    error: str | None = None


class WorkerProviderError(RuntimeError):
    """Raised when every configured coding worker fails."""

    def __init__(
        self,
        attempts: tuple[WorkerAttempt, ...],
    ) -> None:
        self.attempts = attempts

        details = "; ".join(
            (
                f"{attempt.provider}: "
                f"{attempt.error or 'unknown failure'}"
            )
            for attempt in attempts
        )

        super().__init__(
            "All configured coding workers failed. "
            f"Attempts: {details}"
        )


class FallbackWorker(BaseWorker):
    """
    Executes a coding instruction using an ordered worker list.

    Failover occurs when a configured provider worker raises an
    exception and another provider remains available.

    The boundary is intentionally narrow: malformed parsed output,
    test failures, and manager rejections happen after execute()
    returns and therefore never trigger provider failover.
    """

    TRANSIENT_MARKERS = (
        "429",
        "500",
        "502",
        "503",
        "504",
        "deadline_exceeded",
        "deadline exceeded",
        "resource_exhausted",
        "resource exhausted",
        "service unavailable",
        "temporarily unavailable",
        "unavailable",
        "high demand",
        "rate limit",
        "rate_limit",
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "connection refused",
        "remote disconnected",
    )

    def __init__(
        self,
        workers: tuple[
            tuple[str, BaseWorker],
            ...,
        ],
    ) -> None:
        if not workers:
            raise ValueError(
                "At least one worker must be configured."
            )

        normalized: list[
            tuple[str, BaseWorker]
        ] = []

        seen: set[str] = set()

        for provider, worker in workers:
            cleaned_provider = (
                provider.strip().lower()
            )

            if not cleaned_provider:
                raise ValueError(
                    "Worker provider cannot be empty."
                )

            if cleaned_provider in seen:
                raise ValueError(
                    "Worker provider cannot be duplicated: "
                    f"{cleaned_provider}"
                )

            if not isinstance(
                worker,
                BaseWorker,
            ):
                raise TypeError(
                    "Configured worker must implement BaseWorker."
                )

            seen.add(cleaned_provider)

            normalized.append(
                (
                    cleaned_provider,
                    worker,
                )
            )

        self.workers = tuple(normalized)
        self.last_attempts: tuple[
            WorkerAttempt,
            ...,
        ] = ()

    def execute(
        self,
        instruction: str,
    ) -> str:
        cleaned_instruction = (
            instruction.strip()
        )

        if not cleaned_instruction:
            raise ValueError(
                "Worker instruction cannot be empty."
            )

        attempts: list[
            WorkerAttempt
        ] = []

        for index, (
            provider,
            worker,
        ) in enumerate(self.workers):
            try:
                response = worker.execute(
                    cleaned_instruction
                )
            except Exception as exc:
                error = (
                    f"{type(exc).__name__}: {exc}"
                )

                attempts.append(
                    WorkerAttempt(
                        provider=provider,
                        successful=False,
                        error=error,
                    )
                )

                has_fallback = (
                    index
                    < len(self.workers) - 1
                )

                if not has_fallback:
                    self.last_attempts = tuple(
                        attempts
                    )

                    if len(attempts) == 1:
                        raise

                    raise WorkerProviderError(
                        tuple(attempts)
                    ) from exc

                logger.warning(
                    "Atlas worker provider %s "
                    "failed; switching to the next "
                    "configured worker. Failure: %s",
                    provider,
                    error,
                )

                continue

            cleaned_response = (
                response.strip()
            )

            if not cleaned_response:
                error = (
                    "RuntimeError: Worker returned "
                    "an empty response."
                )

                attempts.append(
                    WorkerAttempt(
                        provider=provider,
                        successful=False,
                        error=error,
                    )
                )

                self.last_attempts = tuple(
                    attempts
                )

                raise RuntimeError(
                    "Worker returned an empty response."
                )

            attempts.append(
                WorkerAttempt(
                    provider=provider,
                    successful=True,
                )
            )

            self.last_attempts = tuple(
                attempts
            )

            if index > 0:
                logger.info(
                    "Atlas coding task completed "
                    "using fallback provider %s.",
                    provider,
                )

            return cleaned_response

        self.last_attempts = tuple(
            attempts
        )

        raise WorkerProviderError(
            tuple(attempts)
        )

    @classmethod
    def is_transient(
        cls,
        error: BaseException,
    ) -> bool:
        if isinstance(
            error,
            (
                TimeoutError,
                ConnectionError,
            ),
        ):
            return True

        text = (
            f"{type(error).__name__}: {error}"
            .strip()
            .lower()
        )

        return any(
            marker in text
            for marker in cls.TRANSIENT_MARKERS
        )


__all__ = [
    "FallbackWorker",
    "WorkerAttempt",
    "WorkerProviderError",
]
