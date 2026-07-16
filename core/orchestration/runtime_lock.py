from __future__ import annotations

import fcntl
import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


class RuntimeLockError(RuntimeError):
    """Raised when another Atlas runtime already owns the process lock."""


@dataclass(slots=True, frozen=True)
class RuntimeLockOwner:
    pid: int
    hostname: str
    acquired_at: str
    lock_path: str


class RuntimeProcessLock:
    """
    Linux file lock preventing multiple Atlas orchestrator instances.

    The operating system automatically releases the lock when:
    - the process exits normally,
    - the process crashes,
    - the service is terminated,
    - the AWS server reboots.
    """

    def __init__(
        self,
        lock_path: str | Path = (
            ".atlas_data/continuous_orchestrator.lock"
        ),
    ) -> None:
        self.lock_path = Path(lock_path)
        self._handle: IO[str] | None = None
        self._owner: RuntimeLockOwner | None = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    @property
    def owner(self) -> RuntimeLockOwner | None:
        return self._owner

    def acquire(
        self,
        *,
        blocking: bool = False,
    ) -> RuntimeLockOwner:
        if self.acquired:
            raise RuntimeLockError(
                "Runtime lock is already acquired by this instance."
            )

        self.lock_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        handle = self.lock_path.open(
            mode="a+",
            encoding="utf-8",
        )

        operation = fcntl.LOCK_EX

        if not blocking:
            operation |= fcntl.LOCK_NB

        try:
            fcntl.flock(
                handle.fileno(),
                operation,
            )
        except BlockingIOError as exc:
            existing_owner = self.read_owner()

            handle.close()

            owner_message = (
                self._format_owner(existing_owner)
                if existing_owner is not None
                else "owner details unavailable"
            )

            raise RuntimeLockError(
                "Another Atlas runtime already owns the lock: "
                f"{owner_message}"
            ) from exc
        except Exception:
            handle.close()
            raise

        owner = RuntimeLockOwner(
            pid=os.getpid(),
            hostname=socket.gethostname(),
            acquired_at=datetime.now(
                timezone.utc
            ).isoformat(),
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

    def read_owner(self) -> RuntimeLockOwner | None:
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

            return RuntimeLockOwner(
                pid=int(payload["pid"]),
                hostname=str(payload["hostname"]),
                acquired_at=str(
                    payload["acquired_at"]
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

    def __enter__(self) -> RuntimeProcessLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    @staticmethod
    def _format_owner(
        owner: RuntimeLockOwner | None,
    ) -> str:
        if owner is None:
            return "owner details unavailable"

        return (
            f"pid={owner.pid}, "
            f"hostname={owner.hostname}, "
            f"acquired_at={owner.acquired_at}"
        )
