from __future__ import annotations

import json
import os
import shutil
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from core.orchestration.runtime_service import (
    RuntimeCycleResult,
    RuntimeCycleStatus,
)


@dataclass(slots=True, frozen=True)
class RuntimeHeartbeat:
    service_status: str
    cycle_count: int
    last_cycle_status: str | None
    task_id: str | None
    message: str
    process_id: int
    hostname: str
    started_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class RuntimeAlert:
    alert_id: str
    severity: str
    cycle_status: str
    task_id: str | None
    message: str
    created_at: str
    acknowledged: bool


@dataclass(slots=True, frozen=True)
class CleanupResult:
    scanned_roots: int
    removed_files: int
    removed_directories: int
    reclaimed_bytes: int
    errors: tuple[str, ...]


class RuntimeHeartbeatStore:
    """Atomic JSON persistence for service heartbeat state."""

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/runtime_heartbeat.json"
        ),
    ) -> None:
        self.storage_path = Path(storage_path)
        self._lock = Lock()

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def save(
        self,
        heartbeat: RuntimeHeartbeat,
    ) -> RuntimeHeartbeat:
        with self._lock:
            self._write_payload(
                asdict(heartbeat)
            )

        return heartbeat

    def load(self) -> RuntimeHeartbeat | None:
        if not self.storage_path.exists():
            return None

        with self._lock:
            try:
                payload = json.loads(
                    self.storage_path.read_text(
                        encoding="utf-8"
                    )
                )
            except (
                OSError,
                json.JSONDecodeError,
            ):
                return None

        if not isinstance(payload, dict):
            return None

        try:
            return RuntimeHeartbeat(
                service_status=str(
                    payload["service_status"]
                ),
                cycle_count=int(
                    payload["cycle_count"]
                ),
                last_cycle_status=(
                    str(payload["last_cycle_status"])
                    if payload.get("last_cycle_status")
                    is not None
                    else None
                ),
                task_id=(
                    str(payload["task_id"])
                    if payload.get("task_id")
                    is not None
                    else None
                ),
                message=str(payload["message"]),
                process_id=int(
                    payload["process_id"]
                ),
                hostname=str(payload["hostname"]),
                started_at=str(
                    payload["started_at"]
                ),
                updated_at=str(
                    payload["updated_at"]
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

    def _write_payload(
        self,
        payload: dict[str, Any],
    ) -> None:
        temporary_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix + ".tmp"
            )
        )

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


class RuntimeAlertStore:
    """Bounded persistent alert queue for runtime failures."""

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/runtime_alerts.json"
        ),
        max_alerts: int = 200,
    ) -> None:
        if max_alerts < 1:
            raise ValueError(
                "max_alerts must be at least 1."
            )

        self.storage_path = Path(storage_path)
        self.max_alerts = max_alerts
        self._lock = Lock()

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self._write_data([])

    def add(
        self,
        *,
        severity: str,
        cycle_status: str,
        task_id: str | None,
        message: str,
    ) -> RuntimeAlert:
        now = self._now()

        alert = RuntimeAlert(
            alert_id=(
                f"alert-{now.replace(':', '').replace('.', '')}"
                f"-{os.getpid()}"
            ),
            severity=severity.strip().lower(),
            cycle_status=cycle_status.strip(),
            task_id=task_id,
            message=message.strip(),
            created_at=now,
            acknowledged=False,
        )

        with self._lock:
            alerts = self._read_data()
            alerts.append(asdict(alert))
            alerts = alerts[-self.max_alerts:]
            self._write_data(alerts)

        return alert

    def list_all(self) -> list[RuntimeAlert]:
        with self._lock:
            payloads = self._read_data()

        alerts: list[RuntimeAlert] = []

        for payload in payloads:
            try:
                alerts.append(
                    RuntimeAlert(
                        alert_id=str(
                            payload["alert_id"]
                        ),
                        severity=str(
                            payload["severity"]
                        ),
                        cycle_status=str(
                            payload["cycle_status"]
                        ),
                        task_id=(
                            str(payload["task_id"])
                            if payload.get("task_id")
                            is not None
                            else None
                        ),
                        message=str(
                            payload["message"]
                        ),
                        created_at=str(
                            payload["created_at"]
                        ),
                        acknowledged=bool(
                            payload["acknowledged"]
                        ),
                    )
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

        return alerts

    def list_unacknowledged(
        self,
    ) -> list[RuntimeAlert]:
        return [
            alert
            for alert in self.list_all()
            if not alert.acknowledged
        ]

    def acknowledge_all(self) -> int:
        with self._lock:
            alerts = self._read_data()
            changed = 0

            for payload in alerts:
                if not bool(
                    payload.get(
                        "acknowledged",
                        False,
                    )
                ):
                    payload["acknowledged"] = True
                    changed += 1

            self._write_data(alerts)

        return changed

    def _read_data(
        self,
    ) -> list[dict[str, Any]]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return []

            parsed = json.loads(content)

            if not isinstance(parsed, list):
                return []

            return [
                payload
                for payload in parsed
                if isinstance(payload, dict)
            ]
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return []

    def _write_data(
        self,
        payload: list[dict[str, Any]],
    ) -> None:
        temporary_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix + ".tmp"
            )
        )

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

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


class RuntimeDiskCleaner:
    """
    Safely removes stale contents only inside approved runtime roots.

    Root directories themselves are preserved.
    Symlinks are removed without following their targets.
    """

    def __init__(
        self,
        roots: Iterable[str | Path],
        *,
        minimum_age_seconds: float = 86400.0,
    ) -> None:
        if minimum_age_seconds < 0:
            raise ValueError(
                "minimum_age_seconds cannot be negative."
            )

        self.roots = tuple(
            Path(root).resolve()
            for root in roots
        )
        self.minimum_age_seconds = (
            minimum_age_seconds
        )

    def cleanup(
        self,
        *,
        now_timestamp: float | None = None,
    ) -> CleanupResult:
        current_timestamp = (
            now_timestamp
            if now_timestamp is not None
            else datetime.now(
                timezone.utc
            ).timestamp()
        )

        removed_files = 0
        removed_directories = 0
        reclaimed_bytes = 0
        errors: list[str] = []

        for root in self.roots:
            if not root.exists():
                continue

            if not root.is_dir():
                errors.append(
                    f"Cleanup root is not a directory: {root}"
                )
                continue

            for child in list(root.iterdir()):
                try:
                    age_seconds = (
                        current_timestamp
                        - child.lstat().st_mtime
                    )

                    if (
                        age_seconds
                        < self.minimum_age_seconds
                    ):
                        continue

                    size = self._path_size(child)

                    if child.is_symlink() or child.is_file():
                        child.unlink()
                        removed_files += 1
                    elif child.is_dir():
                        shutil.rmtree(child)
                        removed_directories += 1

                    reclaimed_bytes += size

                except Exception as exc:
                    errors.append(
                        f"{child}: "
                        f"{type(exc).__name__}: {exc}"
                    )

        return CleanupResult(
            scanned_roots=len(self.roots),
            removed_files=removed_files,
            removed_directories=removed_directories,
            reclaimed_bytes=reclaimed_bytes,
            errors=tuple(errors),
        )

    @staticmethod
    def _path_size(
        path: Path,
    ) -> int:
        if path.is_symlink():
            return path.lstat().st_size

        if path.is_file():
            return path.stat().st_size

        total = 0

        for child in path.rglob("*"):
            try:
                if child.is_symlink():
                    total += child.lstat().st_size
                elif child.is_file():
                    total += child.stat().st_size
            except OSError:
                continue

        return total


class RuntimeObserver:
    """
    Records immediate cycle events, heartbeat, alerts, and cleanup.
    """

    ALERT_STATUSES = frozenset(
        {
            RuntimeCycleStatus.FAILED,
            RuntimeCycleStatus.WAITING_FOR_HUMAN,
        }
    )

    def __init__(
        self,
        *,
        heartbeat_store: RuntimeHeartbeatStore,
        alert_store: RuntimeAlertStore,
        disk_cleaner: RuntimeDiskCleaner,
        cleanup_interval_cycles: int = 120,
    ) -> None:
        if cleanup_interval_cycles < 1:
            raise ValueError(
                "cleanup_interval_cycles must be at least 1."
            )

        self.heartbeat_store = heartbeat_store
        self.alert_store = alert_store
        self.disk_cleaner = disk_cleaner
        self.cleanup_interval_cycles = (
            cleanup_interval_cycles
        )

        self.started_at = self._now()
        self.cycle_count = 0

    def mark_started(self) -> RuntimeHeartbeat:
        return self._save_heartbeat(
            service_status="running",
            cycle_status=None,
            task_id=None,
            message=(
                "Atlas continuous runtime started."
            ),
        )

    def handle_cycle(
        self,
        result: RuntimeCycleResult,
    ) -> RuntimeHeartbeat:
        self.cycle_count += 1

        task_id = (
            result.roadmap_task.task_id
            if result.roadmap_task is not None
            else None
        )

        if result.status in self.ALERT_STATUSES:
            severity = (
                "critical"
                if result.status
                == RuntimeCycleStatus.FAILED
                else "warning"
            )

            self.alert_store.add(
                severity=severity,
                cycle_status=result.status.value,
                task_id=task_id,
                message=result.message,
            )

        if (
            self.cycle_count
            % self.cleanup_interval_cycles
            == 0
        ):
            cleanup_result = (
                self.disk_cleaner.cleanup()
            )

            if cleanup_result.errors:
                self.alert_store.add(
                    severity="warning",
                    cycle_status="cleanup_error",
                    task_id=task_id,
                    message="; ".join(
                        cleanup_result.errors
                    ),
                )

        return self._save_heartbeat(
            service_status="running",
            cycle_status=result.status.value,
            task_id=task_id,
            message=result.message,
        )

    def mark_stopped(self) -> RuntimeHeartbeat:
        return self._save_heartbeat(
            service_status="stopped",
            cycle_status=None,
            task_id=None,
            message=(
                "Atlas continuous runtime stopped."
            ),
        )

    def _save_heartbeat(
        self,
        *,
        service_status: str,
        cycle_status: str | None,
        task_id: str | None,
        message: str,
    ) -> RuntimeHeartbeat:
        heartbeat = RuntimeHeartbeat(
            service_status=service_status,
            cycle_count=self.cycle_count,
            last_cycle_status=cycle_status,
            task_id=task_id,
            message=message,
            process_id=os.getpid(),
            hostname=socket.gethostname(),
            started_at=self.started_at,
            updated_at=self._now(),
        )

        return self.heartbeat_store.save(
            heartbeat
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()
