from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


class RoadmapTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    PAUSED = "paused"


@dataclass(slots=True, frozen=True)
class RoadmapTask:
    task_id: str
    title: str
    goal: str
    priority: int
    sequence: int
    depends_on: tuple[str, ...]
    status: RoadmapTaskStatus
    source: str
    blocker_reason: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class RoadmapSelection:
    task: RoadmapTask | None
    pending_count: int
    ready_count: int
    blocked_count: int
    roadmap_complete: bool
    message: str


class RoadmapStoreError(RuntimeError):
    """Raised when persisted roadmap state is invalid."""


class RoadmapTaskStore:
    """
    Persistent JSON-backed store for approved Atlas roadmap tasks.

    The store never creates random tasks. Tasks must be imported or added
    explicitly from architect guidance, roadmap input, or another approved
    source.
    """

    ALLOWED_TRANSITIONS = {
        RoadmapTaskStatus.PENDING: {
            RoadmapTaskStatus.RUNNING,
            RoadmapTaskStatus.BLOCKED,
            RoadmapTaskStatus.PAUSED,
            RoadmapTaskStatus.FAILED,
        },
        RoadmapTaskStatus.RUNNING: {
            RoadmapTaskStatus.COMPLETED,
            RoadmapTaskStatus.FAILED,
            RoadmapTaskStatus.BLOCKED,
            RoadmapTaskStatus.PAUSED,
        },
        RoadmapTaskStatus.BLOCKED: {
            RoadmapTaskStatus.PENDING,
            RoadmapTaskStatus.PAUSED,
            RoadmapTaskStatus.FAILED,
        },
        RoadmapTaskStatus.PAUSED: {
            RoadmapTaskStatus.PENDING,
            RoadmapTaskStatus.BLOCKED,
            RoadmapTaskStatus.FAILED,
        },
        RoadmapTaskStatus.FAILED: {
            RoadmapTaskStatus.PENDING,
            RoadmapTaskStatus.BLOCKED,
        },
        RoadmapTaskStatus.COMPLETED: set(),
    }

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/roadmap_tasks.json"
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
        source: str = "architect",
        task_id: str | None = None,
    ) -> RoadmapTask:
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

        resolved_task_id = (
            task_id.strip()
            if task_id is not None
            else self._generate_task_id()
        )

        if not resolved_task_id:
            raise ValueError("task_id cannot be empty.")

        cleaned_dependencies = tuple(
            dependency.strip()
            for dependency in depends_on
            if dependency.strip()
        )

        if resolved_task_id in cleaned_dependencies:
            raise ValueError(
                "A roadmap task cannot depend on itself."
            )

        now = self._now()

        with self._lock:
            data = self._read_data()

            if resolved_task_id in data:
                raise RoadmapStoreError(
                    f"Roadmap task already exists: {resolved_task_id}"
                )

            missing_dependencies = [
                dependency
                for dependency in cleaned_dependencies
                if dependency not in data
            ]

            if missing_dependencies:
                raise RoadmapStoreError(
                    "Roadmap task depends on missing tasks: "
                    + ", ".join(missing_dependencies)
                )

            sequence = (
                max(
                    (
                        int(record.get("sequence", 0))
                        for record in data.values()
                        if isinstance(record, dict)
                    ),
                    default=0,
                )
                + 1
            )

            task = RoadmapTask(
                task_id=resolved_task_id,
                title=cleaned_title,
                goal=cleaned_goal,
                priority=priority,
                sequence=sequence,
                depends_on=cleaned_dependencies,
                status=RoadmapTaskStatus.PENDING,
                source=cleaned_source,
                blocker_reason=None,
                created_at=now,
                updated_at=now,
            )

            data[resolved_task_id] = self._serialize(task)
            self._write_data(data)

        return task

    def load(
        self,
        task_id: str,
    ) -> RoadmapTask | None:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            raise ValueError("task_id cannot be empty.")

        with self._lock:
            data = self._read_data()
            payload = data.get(cleaned_task_id)

        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise RoadmapStoreError(
                "Stored roadmap task is invalid."
            )

        return self._deserialize(payload)

    def require(
        self,
        task_id: str,
    ) -> RoadmapTask:
        task = self.load(task_id)

        if task is None:
            raise KeyError(
                f"Roadmap task does not exist: {task_id}"
            )

        return task

    def list_all(self) -> list[RoadmapTask]:
        with self._lock:
            data = self._read_data()

        tasks = [
            self._deserialize(payload)
            for payload in data.values()
            if isinstance(payload, dict)
        ]

        return sorted(
            tasks,
            key=lambda task: task.sequence,
        )

    def update_status(
        self,
        task_id: str,
        status: RoadmapTaskStatus,
        *,
        blocker_reason: str | None = None,
    ) -> RoadmapTask:
        with self._lock:
            data = self._read_data()
            payload = data.get(task_id)

            if payload is None:
                raise KeyError(
                    f"Roadmap task does not exist: {task_id}"
                )

            if not isinstance(payload, dict):
                raise RoadmapStoreError(
                    "Stored roadmap task is invalid."
                )

            current = self._deserialize(payload)

            if status != current.status:
                allowed = self.ALLOWED_TRANSITIONS[
                    current.status
                ]

                if status not in allowed:
                    raise RoadmapStoreError(
                        "Invalid roadmap transition: "
                        f"{current.status.value} -> {status.value}"
                    )

            cleaned_blocker = (
                blocker_reason.strip()
                if blocker_reason is not None
                and blocker_reason.strip()
                else None
            )

            if (
                status == RoadmapTaskStatus.BLOCKED
                and cleaned_blocker is None
            ):
                raise ValueError(
                    "Blocked tasks require blocker_reason."
                )

            updated = RoadmapTask(
                task_id=current.task_id,
                title=current.title,
                goal=current.goal,
                priority=current.priority,
                sequence=current.sequence,
                depends_on=current.depends_on,
                status=status,
                source=current.source,
                blocker_reason=(
                    cleaned_blocker
                    if status == RoadmapTaskStatus.BLOCKED
                    else None
                ),
                created_at=current.created_at,
                updated_at=self._now(),
            )

            data[task_id] = self._serialize(updated)
            self._write_data(data)

        return updated

    def retry_failed(
        self,
        task_id: str,
    ) -> RoadmapTask:
        """
        Reset exactly one failed roadmap task to pending.

        Dependencies are not bypassed. The normal roadmap selector
        decides whether the pending task is ready to run.
        """
        with self._lock:
            data = self._read_data()
            payload = data.get(task_id)

            if payload is None:
                raise KeyError(
                    f"Roadmap task does not exist: {task_id}"
                )

            if not isinstance(payload, dict):
                raise RoadmapStoreError(
                    "Stored roadmap task is invalid."
                )

            current = self._deserialize(
                payload
            )

            if (
                current.status
                != RoadmapTaskStatus.FAILED
            ):
                raise RoadmapStoreError(
                    "Only failed roadmap tasks "
                    "can be retried. "
                    f"Current status: "
                    f"{current.status.value}"
                )

            updated = RoadmapTask(
                task_id=current.task_id,
                title=current.title,
                goal=current.goal,
                priority=current.priority,
                sequence=current.sequence,
                depends_on=current.depends_on,
                status=(
                    RoadmapTaskStatus.PENDING
                ),
                source=current.source,
                blocker_reason=None,
                created_at=current.created_at,
                updated_at=self._now(),
            )

            data[task_id] = (
                self._serialize(updated)
            )

            self._write_data(data)

        return updated

    def delete(
        self,
        task_id: str,
    ) -> None:
        with self._lock:
            data = self._read_data()

            if task_id not in data:
                return

            dependents = [
                str(payload.get("task_id", key))
                for key, payload in data.items()
                if isinstance(payload, dict)
                and task_id in payload.get("depends_on", [])
            ]

            if dependents:
                raise RoadmapStoreError(
                    "Cannot delete roadmap task with dependents: "
                    + ", ".join(dependents)
                )

            data.pop(task_id)
            self._write_data(data)

    @staticmethod
    def _serialize(
        task: RoadmapTask,
    ) -> dict[str, Any]:
        payload = asdict(task)
        payload["depends_on"] = list(task.depends_on)
        payload["status"] = task.status.value
        return payload

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> RoadmapTask:
        try:
            return RoadmapTask(
                task_id=str(payload["task_id"]),
                title=str(payload["title"]),
                goal=str(payload["goal"]),
                priority=int(payload["priority"]),
                sequence=int(payload["sequence"]),
                depends_on=tuple(
                    str(value)
                    for value in payload.get(
                        "depends_on",
                        [],
                    )
                ),
                status=RoadmapTaskStatus(
                    payload["status"]
                ),
                source=str(payload["source"]),
                blocker_reason=(
                    str(payload["blocker_reason"])
                    if payload.get("blocker_reason")
                    is not None
                    else None
                ),
                created_at=str(payload["created_at"]),
                updated_at=str(payload["updated_at"]),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise RoadmapStoreError(
                "Stored roadmap task contains invalid data."
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
                raise RoadmapStoreError(
                    "Roadmap store must contain a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RoadmapStoreError(
                "Roadmap store contains invalid JSON."
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
    def _generate_task_id() -> str:
        return f"roadmap-{uuid4().hex[:12]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


class RoadmapTaskSelector:
    """
    Selects the highest-priority ready roadmap task.

    Selection rules:
    - Only PENDING tasks can be selected.
    - Every dependency must be COMPLETED.
    - Failed or blocked dependencies block dependent tasks.
    - Lower priority number means higher priority.
    - Equal priorities preserve insertion sequence.
    - Empty roadmap returns no task and never invents work.
    """

    def __init__(
        self,
        store: RoadmapTaskStore,
    ) -> None:
        self.store = store

    def select_next(self) -> RoadmapSelection:
        tasks = self.store.list_all()

        if not tasks:
            return RoadmapSelection(
                task=None,
                pending_count=0,
                ready_count=0,
                blocked_count=0,
                roadmap_complete=True,
                message=(
                    "Roadmap is empty. Atlas will not create random work."
                ),
            )

        tasks_by_id = {
            task.task_id: task
            for task in tasks
        }

        pending = [
            task
            for task in tasks
            if task.status == RoadmapTaskStatus.PENDING
        ]

        ready: list[RoadmapTask] = []
        blocked_count = 0

        for task in pending:
            dependencies = [
                tasks_by_id[dependency_id]
                for dependency_id in task.depends_on
                if dependency_id in tasks_by_id
            ]

            if len(dependencies) != len(task.depends_on):
                blocked_count += 1
                continue

            if any(
                dependency.status
                in {
                    RoadmapTaskStatus.FAILED,
                    RoadmapTaskStatus.BLOCKED,
                    RoadmapTaskStatus.PAUSED,
                }
                for dependency in dependencies
            ):
                blocked_count += 1
                continue

            if all(
                dependency.status
                == RoadmapTaskStatus.COMPLETED
                for dependency in dependencies
            ):
                ready.append(task)

        ready.sort(
            key=lambda task: (
                task.priority,
                task.sequence,
            )
        )

        selected = (
            ready[0]
            if ready
            else None
        )

        active_count = sum(
            task.status
            in {
                RoadmapTaskStatus.PENDING,
                RoadmapTaskStatus.RUNNING,
                RoadmapTaskStatus.BLOCKED,
                RoadmapTaskStatus.PAUSED,
                RoadmapTaskStatus.FAILED,
            }
            for task in tasks
        )

        roadmap_complete = active_count == 0

        if selected is not None:
            message = (
                "Selected next roadmap task: "
                f"{selected.task_id} - {selected.title}"
            )
        elif roadmap_complete:
            message = (
                "All roadmap tasks are completed. "
                "Atlas will not create random work."
            )
        elif blocked_count > 0:
            message = (
                "No ready roadmap task. Remaining tasks are blocked "
                "or waiting for dependencies."
            )
        else:
            message = (
                "No ready roadmap task is currently available."
            )

        return RoadmapSelection(
            task=selected,
            pending_count=len(pending),
            ready_count=len(ready),
            blocked_count=blocked_count,
            roadmap_complete=roadmap_complete,
            message=message,
        )

    def start_next(self) -> RoadmapSelection:
        selection = self.select_next()

        if selection.task is None:
            return selection

        started = self.store.update_status(
            selection.task.task_id,
            RoadmapTaskStatus.RUNNING,
        )

        return RoadmapSelection(
            task=started,
            pending_count=selection.pending_count,
            ready_count=selection.ready_count,
            blocked_count=selection.blocked_count,
            roadmap_complete=False,
            message=(
                "Started roadmap task: "
                f"{started.task_id} - {started.title}"
            ),
        )
