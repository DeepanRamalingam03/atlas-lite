from __future__ import annotations

import fcntl
import json
import os
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Callable


class ProductionGuardError(RuntimeError):
    """Raised when a production operation is unsafe."""


class RepositoryLockError(ProductionGuardError):
    """Raised when another process owns the repository lock."""


@dataclass(slots=True, frozen=True)
class RepositoryLockOwner:
    pid: int
    hostname: str
    acquired_at: str
    operation: str
    lock_path: str


@dataclass(slots=True, frozen=True)
class DiskPressureStatus:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    free_percent: float
    minimum_free_bytes: int
    minimum_free_percent: float
    safe: bool
    reason: str


@dataclass(slots=True, frozen=True)
class ProductionPreflightResult:
    safe: bool
    branch: str
    repository_clean: bool
    disk_status: DiskPressureStatus
    message: str


DiskUsageProvider = Callable[
    [Path],
    shutil._ntuple_diskusage,
]


class RepositoryOperationLock:
    """
    Cross-process Linux lock for Atlas apply, commit, and push operations.

    flock releases the lock automatically if the owning process exits.
    The JSON payload is only diagnostic owner information.
    """

    def __init__(
        self,
        lock_path: str | Path,
        *,
        operation: str = "release",
    ) -> None:
        cleaned_operation = operation.strip()

        if not cleaned_operation:
            raise ValueError(
                "operation cannot be empty."
            )

        self.lock_path = Path(lock_path)
        self.operation = cleaned_operation
        self._handle: IO[str] | None = None
        self._owner: RepositoryLockOwner | None = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    @property
    def owner(
        self,
    ) -> RepositoryLockOwner | None:
        return self._owner

    def acquire(
        self,
        *,
        blocking: bool = False,
    ) -> RepositoryLockOwner:
        if self.acquired:
            raise RepositoryLockError(
                "This lock instance already owns "
                "the repository operation lock."
            )

        self.lock_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        handle = self.lock_path.open(
            mode="a+",
            encoding="utf-8",
        )

        flock_operation = fcntl.LOCK_EX

        if not blocking:
            flock_operation |= fcntl.LOCK_NB

        try:
            fcntl.flock(
                handle.fileno(),
                flock_operation,
            )
        except BlockingIOError as exc:
            existing_owner = self.read_owner()
            handle.close()

            if existing_owner is None:
                owner_description = (
                    "owner details unavailable"
                )
            else:
                owner_description = (
                    f"pid={existing_owner.pid}, "
                    f"hostname={existing_owner.hostname}, "
                    f"operation={existing_owner.operation}, "
                    f"acquired_at="
                    f"{existing_owner.acquired_at}"
                )

            raise RepositoryLockError(
                "Another Atlas repository operation "
                f"is already active: {owner_description}"
            ) from exc
        except Exception:
            handle.close()
            raise

        owner = RepositoryLockOwner(
            pid=os.getpid(),
            hostname=socket.gethostname(),
            acquired_at=datetime.now(
                timezone.utc
            ).isoformat(),
            operation=self.operation,
            lock_path=str(
                self.lock_path.resolve()
            ),
        )

        handle.seek(0)
        handle.truncate(0)

        json.dump(
            asdict(owner),
            handle,
            indent=2,
            ensure_ascii=False,
        )

        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())

        self._handle = handle
        self._owner = owner

        return owner

    def release(self) -> None:
        handle = self._handle

        if handle is None:
            return

        try:
            handle.seek(0)
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )
            finally:
                handle.close()
                self._handle = None
                self._owner = None

    def read_owner(
        self,
    ) -> RepositoryLockOwner | None:
        if not self.lock_path.exists():
            return None

        try:
            content = self.lock_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return None

            payload = json.loads(content)

            if not isinstance(payload, dict):
                return None

            return RepositoryLockOwner(
                pid=int(payload["pid"]),
                hostname=str(payload["hostname"]),
                acquired_at=str(
                    payload["acquired_at"]
                ),
                operation=str(
                    payload["operation"]
                ),
                lock_path=str(
                    payload["lock_path"]
                ),
            )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

    def __enter__(
        self,
    ) -> RepositoryOperationLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.release()


class DiskPressureGuard:
    """
    Prevents apply/commit/push when server free space is unsafe.

    Both minimum byte and percentage thresholds must pass.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        minimum_free_bytes: int = 268_435_456,
        minimum_free_percent: float = 5.0,
        usage_provider: (
            DiskUsageProvider
        ) = shutil.disk_usage,
    ) -> None:
        if minimum_free_bytes < 0:
            raise ValueError(
                "minimum_free_bytes cannot be negative."
            )

        if not 0 <= minimum_free_percent <= 100:
            raise ValueError(
                "minimum_free_percent must be "
                "between 0 and 100."
            )

        self.path = Path(path).resolve()
        self.minimum_free_bytes = (
            minimum_free_bytes
        )
        self.minimum_free_percent = (
            minimum_free_percent
        )
        self.usage_provider = usage_provider

    def inspect(
        self,
    ) -> DiskPressureStatus:
        usage = self.usage_provider(
            self.path
        )

        free_percent = (
            (usage.free / usage.total) * 100
            if usage.total > 0
            else 0.0
        )

        safe = (
            usage.free
            >= self.minimum_free_bytes
            and free_percent
            >= self.minimum_free_percent
        )

        if safe:
            reason = (
                "Disk capacity is safe for "
                "an autonomous release."
            )
        else:
            reason = (
                "Disk pressure guard blocked release: "
                f"free_bytes={usage.free}, "
                f"free_percent={free_percent:.2f}, "
                f"required_bytes="
                f"{self.minimum_free_bytes}, "
                f"required_percent="
                f"{self.minimum_free_percent:.2f}."
            )

        return DiskPressureStatus(
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            free_percent=free_percent,
            minimum_free_bytes=(
                self.minimum_free_bytes
            ),
            minimum_free_percent=(
                self.minimum_free_percent
            ),
            safe=safe,
            reason=reason,
        )

    def require_safe(
        self,
    ) -> DiskPressureStatus:
        status = self.inspect()

        if not status.safe:
            raise ProductionGuardError(
                status.reason
            )

        return status


class ProductionPreflight:
    """
    Verifies release safety before staged changes are applied.

    Runtime files under ignored directories do not make Git dirty.
    Only tracked changes are checked.
    """

    def __init__(
        self,
        repository_root: str | Path,
        disk_guard: DiskPressureGuard,
        *,
        expected_branch: str,
    ) -> None:
        cleaned_branch = (
            expected_branch.strip()
        )

        if not cleaned_branch:
            raise ValueError(
                "expected_branch cannot be empty."
            )

        self.repository_root = Path(
            repository_root
        ).resolve()
        self.disk_guard = disk_guard
        self.expected_branch = cleaned_branch

    def inspect(
        self,
    ) -> ProductionPreflightResult:
        disk_status = (
            self.disk_guard.inspect()
        )

        branch = self._git(
            "branch",
            "--show-current",
        ).strip()

        tracked_status = self._git(
            "status",
            "--porcelain",
            "--untracked-files=no",
        ).strip()

        repository_clean = (
            tracked_status == ""
        )

        safe = (
            disk_status.safe
            and repository_clean
            and branch
            == self.expected_branch
        )

        reasons: list[str] = []

        if not disk_status.safe:
            reasons.append(
                disk_status.reason
            )

        if not repository_clean:
            reasons.append(
                "Tracked repository changes "
                "already exist before release."
            )

        if branch != self.expected_branch:
            reasons.append(
                "Repository branch mismatch: "
                f"expected={self.expected_branch}, "
                f"actual={branch or 'detached'}."
            )

        return ProductionPreflightResult(
            safe=safe,
            branch=branch,
            repository_clean=repository_clean,
            disk_status=disk_status,
            message=(
                "Production preflight passed."
                if safe
                else " ".join(reasons)
            ),
        )

    def require_safe(
        self,
    ) -> ProductionPreflightResult:
        result = self.inspect()

        if not result.safe:
            raise ProductionGuardError(
                result.message
            )

        return result

    def _git(
        self,
        *arguments: str,
    ) -> str:
        completed = subprocess.run(
            [
                "git",
                *arguments,
            ],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if completed.returncode != 0:
            raise ProductionGuardError(
                "Git preflight command failed:\n"
                f"git {' '.join(arguments)}\n"
                f"{completed.stdout}\n"
                f"{completed.stderr}"
            )

        return completed.stdout


class LockedReleaseCoordinator:
    """
    Decorates the existing ReleaseCoordinator.

    Existing preview, transactional apply, Git commit, and push behaviour
    remain inside the delegate. This class only adds a global lock and
    preflight safety check.
    """

    def __init__(
        self,
        delegate: Any,
        *,
        operation_lock: RepositoryOperationLock,
        preflight: ProductionPreflight,
    ) -> None:
        self.delegate = delegate
        self.operation_lock = operation_lock
        self.preflight = preflight

    def preview(self) -> Any:
        return self.delegate.preview()

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan: Any | None = None,
    ) -> Any:
        with self.operation_lock:
            self.preflight.require_safe()

            return self.delegate.release(
                commit_message=commit_message,
                push=push,
                remote=remote,
                branch=branch,
                diff_plan=diff_plan,
            )
