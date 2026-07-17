from __future__ import annotations

import fcntl
import json
import os
import socket
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


class TokenUsageLedgerError(RuntimeError):
    """Raised when the token usage ledger cannot be read or written."""


@dataclass(slots=True, frozen=True)
class TokenUsageRecord:
    record_id: str
    timestamp: str
    provider: str
    model: str
    success: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    tool_tokens: int = 0
    latency_ms: int = 0
    error_type: str | None = None
    process_id: int = 0
    hostname: str = ""

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError(
                "record_id cannot be empty."
            )

        if not self.provider.strip():
            raise ValueError(
                "provider cannot be empty."
            )

        if not self.model.strip():
            raise ValueError(
                "model cannot be empty."
            )

        numeric_fields = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "tool_tokens": self.tool_tokens,
            "latency_ms": self.latency_ms,
        }

        for name, value in numeric_fields.items():
            if value < 0:
                raise ValueError(
                    f"{name} cannot be negative."
                )

    @classmethod
    def create(
        cls,
        *,
        provider: str,
        model: str,
        success: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        tool_tokens: int = 0,
        latency_ms: int = 0,
        error_type: str | None = None,
    ) -> TokenUsageRecord:
        return cls(
            record_id=(
                "usage-"
                + uuid.uuid4().hex
            ),
            timestamp=datetime.now(
                timezone.utc
            ).isoformat(),
            provider=provider.strip().lower(),
            model=model.strip(),
            success=success,
            input_tokens=max(
                0,
                int(input_tokens or 0),
            ),
            output_tokens=max(
                0,
                int(output_tokens or 0),
            ),
            total_tokens=max(
                0,
                int(total_tokens or 0),
            ),
            cached_input_tokens=max(
                0,
                int(cached_input_tokens or 0),
            ),
            reasoning_tokens=max(
                0,
                int(reasoning_tokens or 0),
            ),
            tool_tokens=max(
                0,
                int(tool_tokens or 0),
            ),
            latency_ms=max(
                0,
                int(latency_ms or 0),
            ),
            error_type=(
                error_type.strip()
                if error_type
                else None
            ),
            process_id=os.getpid(),
            hostname=socket.gethostname(),
        )


@dataclass(slots=True, frozen=True)
class TokenUsageSummary:
    request_count: int
    successful_requests: int
    failed_requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    tool_tokens: int
    total_latency_ms: int

    @property
    def average_latency_ms(self) -> float:
        if self.request_count == 0:
            return 0.0

        return (
            self.total_latency_ms
            / self.request_count
        )


class TokenUsageLedger:
    """
    Process-safe persistent ledger for provider token usage.

    Atlas runtime and Discord run as separate processes. A filesystem lock
    protects read-modify-write operations so their records are not lost.

    Prompts and model responses are deliberately never stored.
    """

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/ai_token_usage.json"
        ),
        *,
        max_records: int = 20_000,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if max_records < 1:
            raise ValueError(
                "max_records must be at least 1."
            )

        self.storage_path = Path(
            storage_path
        )
        self.lock_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix
                + ".lock"
            )
        )
        self.max_records = max_records
        self.clock = clock

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def append(
        self,
        record: TokenUsageRecord,
    ) -> None:
        with self._exclusive_lock():
            records = self._load_unlocked()
            records.append(record)

            if len(records) > self.max_records:
                records = records[
                    -self.max_records:
                ]

            self._save_unlocked(records)

    def list_all(
        self,
    ) -> list[TokenUsageRecord]:
        with self._exclusive_lock():
            return self._load_unlocked()

    def summarize(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        since: datetime | None = None,
    ) -> TokenUsageSummary:
        selected_provider = (
            provider.strip().lower()
            if provider
            else None
        )

        selected_model = (
            model.strip()
            if model
            else None
        )

        records = self.list_all()

        filtered: list[
            TokenUsageRecord
        ] = []

        for record in records:
            if (
                selected_provider is not None
                and record.provider
                != selected_provider
            ):
                continue

            if (
                selected_model is not None
                and record.model
                != selected_model
            ):
                continue

            if since is not None:
                timestamp = datetime.fromisoformat(
                    record.timestamp
                )

                normalized_since = since

                if (
                    normalized_since.tzinfo
                    is None
                ):
                    normalized_since = (
                        normalized_since.replace(
                            tzinfo=timezone.utc
                        )
                    )

                if timestamp < normalized_since:
                    continue

            filtered.append(record)

        return self._summarize_records(
            filtered
        )

    def summarize_by_provider(
        self,
        *,
        since: datetime | None = None,
    ) -> dict[str, TokenUsageSummary]:
        records = self.list_all()
        providers = sorted(
            {
                record.provider
                for record in records
            }
        )

        result: dict[
            str,
            TokenUsageSummary,
        ] = {}

        for provider in providers:
            selected = [
                record
                for record in records
                if (
                    record.provider
                    == provider
                    and self._is_since(
                        record,
                        since,
                    )
                )
            ]

            result[provider] = (
                self._summarize_records(
                    selected
                )
            )

        return result

    def clear(self) -> None:
        with self._exclusive_lock():
            self._save_unlocked([])

    def elapsed_milliseconds(
        self,
        started_at: float,
    ) -> int:
        elapsed = (
            self.clock() - started_at
        )

        return max(
            0,
            round(elapsed * 1000),
        )

    def _load_unlocked(
        self,
    ) -> list[TokenUsageRecord]:
        if not self.storage_path.exists():
            return []

        try:
            raw_payload = json.loads(
                self.storage_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise TokenUsageLedgerError(
                "Unable to read token usage ledger: "
                f"{exc}"
            ) from exc

        if not isinstance(raw_payload, dict):
            raise TokenUsageLedgerError(
                "Token usage ledger root "
                "must be an object."
            )

        raw_records = raw_payload.get(
            "records",
            [],
        )

        if not isinstance(raw_records, list):
            raise TokenUsageLedgerError(
                "Token usage ledger records "
                "must be a list."
            )

        records: list[
            TokenUsageRecord
        ] = []

        for item in raw_records:
            if not isinstance(item, dict):
                continue

            try:
                records.append(
                    TokenUsageRecord(
                        record_id=str(
                            item.get(
                                "record_id",
                                "",
                            )
                        ),
                        timestamp=str(
                            item.get(
                                "timestamp",
                                "",
                            )
                        ),
                        provider=str(
                            item.get(
                                "provider",
                                "",
                            )
                        ),
                        model=str(
                            item.get(
                                "model",
                                "",
                            )
                        ),
                        success=bool(
                            item.get(
                                "success",
                                False,
                            )
                        ),
                        input_tokens=int(
                            item.get(
                                "input_tokens",
                                0,
                            )
                            or 0
                        ),
                        output_tokens=int(
                            item.get(
                                "output_tokens",
                                0,
                            )
                            or 0
                        ),
                        total_tokens=int(
                            item.get(
                                "total_tokens",
                                0,
                            )
                            or 0
                        ),
                        cached_input_tokens=int(
                            item.get(
                                "cached_input_tokens",
                                0,
                            )
                            or 0
                        ),
                        reasoning_tokens=int(
                            item.get(
                                "reasoning_tokens",
                                0,
                            )
                            or 0
                        ),
                        tool_tokens=int(
                            item.get(
                                "tool_tokens",
                                0,
                            )
                            or 0
                        ),
                        latency_ms=int(
                            item.get(
                                "latency_ms",
                                0,
                            )
                            or 0
                        ),
                        error_type=(
                            str(
                                item[
                                    "error_type"
                                ]
                            )
                            if item.get(
                                "error_type"
                            )
                            else None
                        ),
                        process_id=int(
                            item.get(
                                "process_id",
                                0,
                            )
                            or 0
                        ),
                        hostname=str(
                            item.get(
                                "hostname",
                                "",
                            )
                        ),
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        return records

    def _save_unlocked(
        self,
        records: Iterable[
            TokenUsageRecord
        ],
    ) -> None:
        payload = {
            "version": 1,
            "records": [
                asdict(record)
                for record in records
            ],
        }

        temporary_path = (
            self.storage_path.with_name(
                self.storage_path.name
                + f".{os.getpid()}.tmp"
            )
        )

        try:
            temporary_path.write_text(
                json.dumps(
                    payload,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            temporary_path.replace(
                self.storage_path
            )
        except OSError as exc:
            raise TokenUsageLedgerError(
                "Unable to write token usage ledger: "
                f"{exc}"
            ) from exc
        finally:
            temporary_path.unlink(
                missing_ok=True
            )

    def _exclusive_lock(self):
        ledger = self

        class LedgerLock:
            def __enter__(
                self,
            ):
                ledger.lock_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                self.handle = open(
                    ledger.lock_path,
                    "a+",
                    encoding="utf-8",
                )

                fcntl.flock(
                    self.handle.fileno(),
                    fcntl.LOCK_EX,
                )

                return self

            def __exit__(
                self,
                exc_type,
                exc,
                traceback,
            ) -> None:
                fcntl.flock(
                    self.handle.fileno(),
                    fcntl.LOCK_UN,
                )

                self.handle.close()

        return LedgerLock()

    @staticmethod
    def _is_since(
        record: TokenUsageRecord,
        since: datetime | None,
    ) -> bool:
        if since is None:
            return True

        normalized_since = since

        if normalized_since.tzinfo is None:
            normalized_since = (
                normalized_since.replace(
                    tzinfo=timezone.utc
                )
            )

        try:
            record_time = datetime.fromisoformat(
                record.timestamp
            )
        except ValueError:
            return False

        return record_time >= normalized_since

    @staticmethod
    def _summarize_records(
        records: Iterable[
            TokenUsageRecord
        ],
    ) -> TokenUsageSummary:
        materialized = list(records)

        return TokenUsageSummary(
            request_count=len(materialized),
            successful_requests=sum(
                record.success
                for record in materialized
            ),
            failed_requests=sum(
                not record.success
                for record in materialized
            ),
            input_tokens=sum(
                record.input_tokens
                for record in materialized
            ),
            output_tokens=sum(
                record.output_tokens
                for record in materialized
            ),
            total_tokens=sum(
                record.total_tokens
                for record in materialized
            ),
            cached_input_tokens=sum(
                record.cached_input_tokens
                for record in materialized
            ),
            reasoning_tokens=sum(
                record.reasoning_tokens
                for record in materialized
            ),
            tool_tokens=sum(
                record.tool_tokens
                for record in materialized
            ),
            total_latency_ms=sum(
                record.latency_ms
                for record in materialized
            ),
        )


__all__ = [
    "TokenUsageLedger",
    "TokenUsageLedgerError",
    "TokenUsageRecord",
    "TokenUsageSummary",
]
