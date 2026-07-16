from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    HUMAN_BLOCKER = "human_blocker"
    PERMANENT = "permanent"


@dataclass(slots=True, frozen=True)
class FailureClassification:
    failure_class: FailureClass
    reason: str

    @property
    def retryable(self) -> bool:
        return self.failure_class == FailureClass.TRANSIENT

    @property
    def requires_human(self) -> bool:
        return self.failure_class == FailureClass.HUMAN_BLOCKER


@dataclass(slots=True, frozen=True)
class RetryState:
    task_id: str
    attempt_count: int
    next_retry_at: str | None
    last_error: str | None
    exhausted: bool
    updated_at: str


@dataclass(slots=True, frozen=True)
class RetryDecision:
    retry: bool
    exhausted: bool
    delay_seconds: float
    next_retry_at: str | None
    attempt_count: int
    classification: FailureClassification
    message: str


class RetryStateStoreError(RuntimeError):
    """Raised when persisted retry state is invalid."""


class FailureClassifier:
    """
    Classifies runtime failures without relying on provider-specific classes.

    Human blockers are never retried automatically.
    Transient infrastructure failures receive bounded retries.
    Unknown implementation failures fail safely instead of looping forever.
    """

    HUMAN_PATTERNS = (
        "human intervention",
        "human approval",
        "approval required",
        "requires approval",
        "login required",
        "authentication required",
        "otp",
        "mfa",
        "captcha",
        "credential",
        "secret required",
        "api key is missing",
        "missing api key",
        "constitution",
        "production deployment",
        "paid resource",
        "live trading",
        "risk-limit",
        "risk limit",
        "permission denied",
        "access denied",
    )

    TRANSIENT_PATTERNS = (
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "connection aborted",
        "connection error",
        "network error",
        "temporary failure",
        "temporarily unavailable",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "rate limit",
        "rate-limit",
        "too many requests",
        "429",
        "502",
        "503",
        "504",
        "remote disconnected",
        "dns",
        "name resolution",
        "try again",
        "server error",
        "internal server error",
        "git push failed",
        "could not resolve host",
        "failed to connect",
    )

    PERMANENT_PATTERNS = (
        "decision: rejected",
        "validation failed",
        "tests failed",
        "syntaxerror",
        "typeerror",
        "valueerror",
        "assertionerror",
        "unsafe file path",
        "invalid json",
        "no file changes",
        "produced no file changes",
        "manager approval",
        "unsupported",
        "invalid transition",
    )

    def classify(
        self,
        error: str | BaseException,
    ) -> FailureClassification:
        if isinstance(error, BaseException):
            text = (
                f"{type(error).__name__}: {error}"
            )
        else:
            text = str(error)

        normalized = text.strip().lower()

        if any(
            pattern in normalized
            for pattern in self.HUMAN_PATTERNS
        ):
            return FailureClassification(
                failure_class=FailureClass.HUMAN_BLOCKER,
                reason=(
                    "Failure requires explicit human action."
                ),
            )

        if any(
            pattern in normalized
            for pattern in self.TRANSIENT_PATTERNS
        ):
            return FailureClassification(
                failure_class=FailureClass.TRANSIENT,
                reason=(
                    "Failure appears temporary and can be retried."
                ),
            )

        if any(
            pattern in normalized
            for pattern in self.PERMANENT_PATTERNS
        ):
            return FailureClassification(
                failure_class=FailureClass.PERMANENT,
                reason=(
                    "Failure requires implementation correction "
                    "rather than automatic retry."
                ),
            )

        return FailureClassification(
            failure_class=FailureClass.PERMANENT,
            reason=(
                "Unknown failure is treated as permanent "
                "to prevent an infinite retry loop."
            ),
        )


class RetryStateStore:
    """Thread-safe JSON persistence for roadmap retry state."""

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/runtime_retries.json"
        ),
    ) -> None:
        self.storage_path = Path(storage_path)
        self._lock = Lock()

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self._write_data({})

    def load(
        self,
        task_id: str,
    ) -> RetryState | None:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            raise ValueError(
                "task_id cannot be empty."
            )

        with self._lock:
            payload = self._read_data().get(
                cleaned_task_id
            )

        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise RetryStateStoreError(
                "Stored retry state is invalid."
            )

        return self._deserialize(payload)

    def require(
        self,
        task_id: str,
    ) -> RetryState:
        state = self.load(task_id)

        if state is None:
            raise KeyError(
                f"Retry state does not exist: {task_id}"
            )

        return state

    def save(
        self,
        *,
        task_id: str,
        attempt_count: int,
        next_retry_at: str | None,
        last_error: str | None,
        exhausted: bool,
    ) -> RetryState:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            raise ValueError(
                "task_id cannot be empty."
            )

        if attempt_count < 0:
            raise ValueError(
                "attempt_count cannot be negative."
            )

        state = RetryState(
            task_id=cleaned_task_id,
            attempt_count=attempt_count,
            next_retry_at=next_retry_at,
            last_error=last_error,
            exhausted=exhausted,
            updated_at=self._now(),
        )

        with self._lock:
            data = self._read_data()
            data[cleaned_task_id] = asdict(state)
            self._write_data(data)

        return state

    def clear(
        self,
        task_id: str,
    ) -> None:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            raise ValueError(
                "task_id cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            data.pop(cleaned_task_id, None)
            self._write_data(data)

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> RetryState:
        try:
            return RetryState(
                task_id=str(payload["task_id"]),
                attempt_count=int(
                    payload["attempt_count"]
                ),
                next_retry_at=(
                    str(payload["next_retry_at"])
                    if payload.get("next_retry_at")
                    is not None
                    else None
                ),
                last_error=(
                    str(payload["last_error"])
                    if payload.get("last_error")
                    is not None
                    else None
                ),
                exhausted=bool(
                    payload["exhausted"]
                ),
                updated_at=str(
                    payload["updated_at"]
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise RetryStateStoreError(
                "Stored retry state contains invalid data."
            ) from exc

    def _read_data(
        self,
    ) -> dict[str, dict[str, Any]]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return {}

            parsed = json.loads(content)

            if not isinstance(parsed, dict):
                raise RetryStateStoreError(
                    "Retry store must contain a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RetryStateStoreError(
                "Retry store contains invalid JSON."
            ) from exc

    def _write_data(
        self,
        data: dict[str, dict[str, Any]],
    ) -> None:
        temporary_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix + ".tmp"
            )
        )

        temporary_path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.storage_path
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


class RuntimeRetryPolicy:
    """
    Bounded exponential-backoff retry policy.

    max_attempts includes the original execution.
    Example: max_attempts=4 permits one initial attempt and three retries.
    """

    def __init__(
        self,
        *,
        state_store: RetryStateStore | None = None,
        classifier: FailureClassifier | None = None,
        max_attempts: int = 1,
        initial_delay_seconds: float = 30.0,
        multiplier: float = 2.0,
        max_delay_seconds: float = 900.0,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(
                "max_attempts must be at least 1."
            )

        if initial_delay_seconds < 0:
            raise ValueError(
                "initial_delay_seconds cannot be negative."
            )

        if multiplier < 1:
            raise ValueError(
                "multiplier must be at least 1."
            )

        if max_delay_seconds < 0:
            raise ValueError(
                "max_delay_seconds cannot be negative."
            )

        self.state_store = (
            state_store or RetryStateStore()
        )
        self.classifier = (
            classifier or FailureClassifier()
        )
        self.max_attempts = max_attempts
        self.initial_delay_seconds = (
            initial_delay_seconds
        )
        self.multiplier = multiplier
        self.max_delay_seconds = max_delay_seconds

    def register_failure(
        self,
        task_id: str,
        error: str | BaseException,
        *,
        now: datetime | None = None,
    ) -> RetryDecision:
        classification = self.classifier.classify(
            error
        )

        existing = self.state_store.load(
            task_id
        )

        attempt_count = (
            existing.attempt_count + 1
            if existing is not None
            else 1
        )

        error_text = (
            f"{type(error).__name__}: {error}"
            if isinstance(error, BaseException)
            else str(error)
        ).strip()

        if not classification.retryable:
            self.state_store.save(
                task_id=task_id,
                attempt_count=attempt_count,
                next_retry_at=None,
                last_error=error_text,
                exhausted=True,
            )

            return RetryDecision(
                retry=False,
                exhausted=True,
                delay_seconds=0,
                next_retry_at=None,
                attempt_count=attempt_count,
                classification=classification,
                message=classification.reason,
            )

        if attempt_count >= self.max_attempts:
            self.state_store.save(
                task_id=task_id,
                attempt_count=attempt_count,
                next_retry_at=None,
                last_error=error_text,
                exhausted=True,
            )

            return RetryDecision(
                retry=False,
                exhausted=True,
                delay_seconds=0,
                next_retry_at=None,
                attempt_count=attempt_count,
                classification=classification,
                message=(
                    "Automatic retry limit reached after "
                    f"{attempt_count} attempt(s)."
                ),
            )

        retry_number = attempt_count - 1

        delay_seconds = min(
            self.initial_delay_seconds
            * (self.multiplier ** retry_number),
            self.max_delay_seconds,
        )

        resolved_now = (
            now or datetime.now(timezone.utc)
        )

        next_retry_at = (
            resolved_now
            + timedelta(seconds=delay_seconds)
        ).isoformat()

        self.state_store.save(
            task_id=task_id,
            attempt_count=attempt_count,
            next_retry_at=next_retry_at,
            last_error=error_text,
            exhausted=False,
        )

        return RetryDecision(
            retry=True,
            exhausted=False,
            delay_seconds=delay_seconds,
            next_retry_at=next_retry_at,
            attempt_count=attempt_count,
            classification=classification,
            message=(
                "Transient failure scheduled for retry "
                f"in {delay_seconds:g} second(s)."
            ),
        )

    def is_ready(
        self,
        task_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        state = self.state_store.load(task_id)

        if state is None:
            return True

        if state.exhausted:
            return False

        if state.next_retry_at is None:
            return True

        try:
            retry_at = datetime.fromisoformat(
                state.next_retry_at
            )
        except ValueError as exc:
            raise RetryStateStoreError(
                "Retry timestamp is invalid."
            ) from exc

        resolved_now = (
            now or datetime.now(timezone.utc)
        )

        return resolved_now >= retry_at

    def seconds_until_ready(
        self,
        task_id: str,
        *,
        now: datetime | None = None,
    ) -> float:
        state = self.state_store.load(task_id)

        if (
            state is None
            or state.next_retry_at is None
        ):
            return 0.0

        retry_at = datetime.fromisoformat(
            state.next_retry_at
        )

        resolved_now = (
            now or datetime.now(timezone.utc)
        )

        return max(
            0.0,
            (retry_at - resolved_now).total_seconds(),
        )

    def clear_success(
        self,
        task_id: str,
    ) -> None:
        self.state_store.clear(task_id)
