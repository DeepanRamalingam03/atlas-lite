from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from core.orchestration.roadmap import (
    RoadmapTaskStore,
)


class ArchitectDirectiveStatus(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class ArchitectDirective:
    directive_id: str
    title: str
    goal: str
    priority: int
    depends_on: tuple[str, ...]
    status: ArchitectDirectiveStatus
    source: str
    roadmap_task_id: str | None
    error: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class DirectiveImportResult:
    imported: tuple[ArchitectDirective, ...]
    failed: tuple[ArchitectDirective, ...]
    pending_count: int

    @property
    def imported_count(self) -> int:
        return len(self.imported)

    @property
    def failed_count(self) -> int:
        return len(self.failed)


class ArchitectDirectiveStoreError(RuntimeError):
    """Raised when the architect directive inbox is invalid."""


class ArchitectDirectiveStore:
    """
    Persistent inbox for approved architect directives.

    Directives are explicit work inputs. Atlas never invents directives.
    """

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/architect_directives.json"
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

    def create(
        self,
        title: str,
        goal: str,
        *,
        priority: int = 100,
        depends_on: tuple[str, ...] = (),
        source: str = "chatgpt-architect",
        directive_id: str | None = None,
    ) -> ArchitectDirective:
        cleaned_title = title.strip()
        cleaned_goal = goal.strip()
        cleaned_source = source.strip()

        if not cleaned_title:
            raise ValueError("title cannot be empty.")

        if not cleaned_goal:
            raise ValueError("goal cannot be empty.")

        if not cleaned_source:
            raise ValueError("source cannot be empty.")

        if priority < 0:
            raise ValueError("priority cannot be negative.")

        resolved_id = (
            directive_id.strip()
            if directive_id is not None
            else self._generate_id()
        )

        if not resolved_id:
            raise ValueError(
                "directive_id cannot be empty."
            )

        dependencies = tuple(
            dependency.strip()
            for dependency in depends_on
            if dependency.strip()
        )

        now = self._now()

        directive = ArchitectDirective(
            directive_id=resolved_id,
            title=cleaned_title,
            goal=cleaned_goal,
            priority=priority,
            depends_on=dependencies,
            status=ArchitectDirectiveStatus.PENDING,
            source=cleaned_source,
            roadmap_task_id=None,
            error=None,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            data = self._read_data()

            if resolved_id in data:
                raise ArchitectDirectiveStoreError(
                    "Architect directive already exists: "
                    f"{resolved_id}"
                )

            data[resolved_id] = self._serialize(
                directive
            )
            self._write_data(data)

        return directive

    def load(
        self,
        directive_id: str,
    ) -> ArchitectDirective | None:
        cleaned_id = directive_id.strip()

        if not cleaned_id:
            raise ValueError(
                "directive_id cannot be empty."
            )

        with self._lock:
            payload = self._read_data().get(
                cleaned_id
            )

        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise ArchitectDirectiveStoreError(
                "Stored architect directive is invalid."
            )

        return self._deserialize(payload)

    def require(
        self,
        directive_id: str,
    ) -> ArchitectDirective:
        directive = self.load(directive_id)

        if directive is None:
            raise KeyError(
                "Architect directive does not exist: "
                f"{directive_id}"
            )

        return directive

    def list_all(self) -> list[ArchitectDirective]:
        with self._lock:
            data = self._read_data()

        directives = [
            self._deserialize(payload)
            for payload in data.values()
            if isinstance(payload, dict)
        ]

        return sorted(
            directives,
            key=lambda directive: (
                directive.created_at,
                directive.directive_id,
            ),
        )

    def list_pending(
        self,
    ) -> list[ArchitectDirective]:
        return [
            directive
            for directive in self.list_all()
            if directive.status
            == ArchitectDirectiveStatus.PENDING
        ]

    def mark_imported(
        self,
        directive_id: str,
        roadmap_task_id: str,
    ) -> ArchitectDirective:
        cleaned_task_id = roadmap_task_id.strip()

        if not cleaned_task_id:
            raise ValueError(
                "roadmap_task_id cannot be empty."
            )

        return self._update(
            directive_id=directive_id,
            status=ArchitectDirectiveStatus.IMPORTED,
            roadmap_task_id=cleaned_task_id,
            error=None,
        )

    def mark_failed(
        self,
        directive_id: str,
        error: str,
    ) -> ArchitectDirective:
        cleaned_error = error.strip()

        if not cleaned_error:
            raise ValueError("error cannot be empty.")

        return self._update(
            directive_id=directive_id,
            status=ArchitectDirectiveStatus.FAILED,
            roadmap_task_id=None,
            error=cleaned_error,
        )

    def retry(
        self,
        directive_id: str,
    ) -> ArchitectDirective:
        directive = self.require(
            directive_id
        )

        if (
            directive.status
            != ArchitectDirectiveStatus.FAILED
        ):
            raise ArchitectDirectiveStoreError(
                "Only failed directives can be retried."
            )

        return self._update(
            directive_id=directive_id,
            status=ArchitectDirectiveStatus.PENDING,
            roadmap_task_id=None,
            error=None,
        )

    def _update(
        self,
        *,
        directive_id: str,
        status: ArchitectDirectiveStatus,
        roadmap_task_id: str | None,
        error: str | None,
    ) -> ArchitectDirective:
        with self._lock:
            data = self._read_data()
            payload = data.get(directive_id)

            if payload is None:
                raise KeyError(
                    "Architect directive does not exist: "
                    f"{directive_id}"
                )

            if not isinstance(payload, dict):
                raise ArchitectDirectiveStoreError(
                    "Stored architect directive is invalid."
                )

            current = self._deserialize(payload)

            updated = ArchitectDirective(
                directive_id=current.directive_id,
                title=current.title,
                goal=current.goal,
                priority=current.priority,
                depends_on=current.depends_on,
                status=status,
                source=current.source,
                roadmap_task_id=roadmap_task_id,
                error=error,
                created_at=current.created_at,
                updated_at=self._now(),
            )

            data[directive_id] = self._serialize(
                updated
            )
            self._write_data(data)

        return updated

    @staticmethod
    def _serialize(
        directive: ArchitectDirective,
    ) -> dict[str, Any]:
        payload = asdict(directive)
        payload["depends_on"] = list(
            directive.depends_on
        )
        payload["status"] = directive.status.value
        return payload

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> ArchitectDirective:
        try:
            return ArchitectDirective(
                directive_id=str(
                    payload["directive_id"]
                ),
                title=str(payload["title"]),
                goal=str(payload["goal"]),
                priority=int(payload["priority"]),
                depends_on=tuple(
                    str(value)
                    for value in payload.get(
                        "depends_on",
                        [],
                    )
                ),
                status=ArchitectDirectiveStatus(
                    payload["status"]
                ),
                source=str(payload["source"]),
                roadmap_task_id=(
                    str(payload["roadmap_task_id"])
                    if payload.get("roadmap_task_id")
                    is not None
                    else None
                ),
                error=(
                    str(payload["error"])
                    if payload.get("error")
                    is not None
                    else None
                ),
                created_at=str(
                    payload["created_at"]
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
            raise ArchitectDirectiveStoreError(
                "Stored architect directive "
                "contains invalid data."
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
                raise ArchitectDirectiveStoreError(
                    "Architect directive store must "
                    "contain a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise ArchitectDirectiveStoreError(
                "Architect directive store "
                "contains invalid JSON."
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
    def _generate_id() -> str:
        return f"directive-{uuid4().hex[:12]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


class RoadmapDirectiveImporter:
    """
    Converts pending architect directives into persistent roadmap tasks.
    """

    def __init__(
        self,
        directive_store: ArchitectDirectiveStore,
        roadmap_store: RoadmapTaskStore,
    ) -> None:
        self.directive_store = directive_store
        self.roadmap_store = roadmap_store

    def import_pending(
        self,
    ) -> DirectiveImportResult:
        imported: list[ArchitectDirective] = []
        failed: list[ArchitectDirective] = []

        for directive in (
            self.directive_store.list_pending()
        ):
            roadmap_task_id = self._task_id(
                directive.directive_id
            )

            try:
                existing = self.roadmap_store.load(
                    roadmap_task_id
                )

                if existing is None:
                    self.roadmap_store.create(
                        title=directive.title,
                        goal=directive.goal,
                        priority=directive.priority,
                        depends_on=directive.depends_on,
                        source=directive.source,
                        task_id=roadmap_task_id,
                    )

                imported_directive = (
                    self.directive_store.mark_imported(
                        directive.directive_id,
                        roadmap_task_id,
                    )
                )

                imported.append(
                    imported_directive
                )

            except Exception as exc:
                failed_directive = (
                    self.directive_store.mark_failed(
                        directive.directive_id,
                        (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    )
                )

                failed.append(failed_directive)

        pending_count = len(
            self.directive_store.list_pending()
        )

        return DirectiveImportResult(
            imported=tuple(imported),
            failed=tuple(failed),
            pending_count=pending_count,
        )

    @staticmethod
    def _task_id(
        directive_id: str,
    ) -> str:
        return f"directive-task-{directive_id}"
