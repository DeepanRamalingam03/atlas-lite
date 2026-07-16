from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(slots=True, frozen=True)
class ProjectMemorySnapshot:
    project_root: str
    fingerprint: str
    context: str
    created_at: str


class ProjectMemory:
    """
    Thread-safe JSON-backed project context memory.

    Stores the latest generated project context and its SHA-256
    fingerprint. Secrets must never be included in the supplied context.
    """

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/project_memory.json"
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

    def save(
        self,
        project_root: str | Path,
        context: str,
    ) -> ProjectMemorySnapshot:
        cleaned_context = context.strip()

        if not cleaned_context:
            raise ValueError(
                "Project context cannot be empty."
            )

        normalized_root = str(
            Path(project_root).resolve()
        )

        snapshot = ProjectMemorySnapshot(
            project_root=normalized_root,
            fingerprint=self.fingerprint(
                cleaned_context
            ),
            context=cleaned_context,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        with self._lock:
            data = self._read_data()
            data[normalized_root] = asdict(snapshot)
            self._write_data(data)

        return snapshot

    def load(
        self,
        project_root: str | Path,
    ) -> ProjectMemorySnapshot | None:
        normalized_root = str(
            Path(project_root).resolve()
        )

        with self._lock:
            data = self._read_data()
            raw_snapshot = data.get(normalized_root)

        if not isinstance(raw_snapshot, dict):
            return None

        project_root_value = raw_snapshot.get(
            "project_root"
        )
        fingerprint_value = raw_snapshot.get(
            "fingerprint"
        )
        context_value = raw_snapshot.get(
            "context"
        )
        created_at_value = raw_snapshot.get(
            "created_at"
        )

        if not all(
            isinstance(value, str)
            for value in (
                project_root_value,
                fingerprint_value,
                context_value,
                created_at_value,
            )
        ):
            raise RuntimeError(
                "Stored project memory snapshot is invalid."
            )

        return ProjectMemorySnapshot(
            project_root=project_root_value,
            fingerprint=fingerprint_value,
            context=context_value,
            created_at=created_at_value,
        )

    def is_current(
        self,
        project_root: str | Path,
        context: str,
    ) -> bool:
        snapshot = self.load(project_root)

        if snapshot is None:
            return False

        return snapshot.fingerprint == self.fingerprint(
            context.strip()
        )

    def clear(
        self,
        project_root: str | Path,
    ) -> None:
        normalized_root = str(
            Path(project_root).resolve()
        )

        with self._lock:
            data = self._read_data()
            data.pop(normalized_root, None)
            self._write_data(data)

    @staticmethod
    def fingerprint(context: str) -> str:
        return hashlib.sha256(
            context.encode("utf-8")
        ).hexdigest()

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
                raise RuntimeError(
                    "Project memory root must be "
                    "a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Project memory file contains "
                f"invalid JSON: {self.storage_path}"
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
