from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from core.orchestration.models import (
    WorkflowProgress,
    WorkflowRecord,
    WorkflowStatus,
)


class WorkflowStateError(RuntimeError):
    """Raised when workflow state is invalid or cannot be changed."""


class WorkflowStateStore:
    """
    Thread-safe JSON-backed orchestration workflow storage.

    A workflow can survive:
    - Discord bot restart,
    - Python process restart,
    - AWS server reboot,
    - human approval wait,
    - temporary worker failure.
    """

    ALLOWED_TRANSITIONS = {
        WorkflowStatus.CREATED: {
            WorkflowStatus.PLANNING,
            WorkflowStatus.STOPPED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.PLANNING: {
            WorkflowStatus.EXECUTING,
            WorkflowStatus.STOPPED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.EXECUTING: {
            WorkflowStatus.VALIDATING,
            WorkflowStatus.EXECUTING,
            WorkflowStatus.STOPPED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.VALIDATING: {
            WorkflowStatus.REVIEWING,
            WorkflowStatus.EXECUTING,
            WorkflowStatus.STOPPED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.REVIEWING: {
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.EXECUTING,
            WorkflowStatus.STOPPED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.WAITING_APPROVAL: {
            WorkflowStatus.APPROVED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.STOPPED,
        },
        WorkflowStatus.APPROVED: {
            WorkflowStatus.APPLYING,
            WorkflowStatus.STOPPED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.APPLYING: {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        },
        WorkflowStatus.REJECTED: set(),
        WorkflowStatus.COMPLETED: set(),
        WorkflowStatus.FAILED: set(),
        WorkflowStatus.STOPPED: set(),
    }

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/orchestration_workflows.json"
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
        user_id: int,
        goal: str,
        workflow_id: str | None = None,
    ) -> WorkflowRecord:
        cleaned_goal = goal.strip()

        if user_id < 1:
            raise ValueError("user_id must be positive.")

        if not cleaned_goal:
            raise ValueError("Workflow goal cannot be empty.")

        resolved_workflow_id = (
            workflow_id.strip()
            if workflow_id is not None
            else self._generate_workflow_id()
        )

        if not resolved_workflow_id:
            raise ValueError(
                "workflow_id cannot be empty."
            )

        now = self._now()

        record = WorkflowRecord(
            workflow_id=resolved_workflow_id,
            user_id=user_id,
            goal=cleaned_goal,
            plan_id=None,
            status=WorkflowStatus.CREATED,
            current_task_id=None,
            approval_fingerprint=None,
            summary="Workflow created.",
            error=None,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            data = self._read_data()

            if resolved_workflow_id in data:
                raise WorkflowStateError(
                    "Workflow already exists: "
                    f"{resolved_workflow_id}"
                )

            data[resolved_workflow_id] = (
                self._serialize(record)
            )

            self._write_data(data)

        return record

    def load(
        self,
        workflow_id: str,
    ) -> WorkflowRecord | None:
        cleaned_workflow_id = workflow_id.strip()

        if not cleaned_workflow_id:
            raise ValueError(
                "workflow_id cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            raw_record = data.get(
                cleaned_workflow_id
            )

        if raw_record is None:
            return None

        if not isinstance(raw_record, dict):
            raise WorkflowStateError(
                "Stored workflow record is invalid."
            )

        return self._deserialize(raw_record)

    def require(
        self,
        workflow_id: str,
    ) -> WorkflowRecord:
        record = self.load(workflow_id)

        if record is None:
            raise KeyError(
                f"Workflow does not exist: {workflow_id}"
            )

        return record

    def update(
        self,
        workflow_id: str,
        *,
        status: WorkflowStatus | None = None,
        plan_id: str | None = None,
        current_task_id: int | None = None,
        approval_fingerprint: str | None = None,
        summary: str | None = None,
        error: str | None = None,
        clear_current_task: bool = False,
        clear_approval: bool = False,
        clear_error: bool = False,
    ) -> WorkflowRecord:
        with self._lock:
            data = self._read_data()
            raw_record = data.get(workflow_id)

            if raw_record is None:
                raise KeyError(
                    f"Workflow does not exist: {workflow_id}"
                )

            if not isinstance(raw_record, dict):
                raise WorkflowStateError(
                    "Stored workflow record is invalid."
                )

            current = self._deserialize(raw_record)

            next_status = (
                status
                if status is not None
                else current.status
            )

            if status is not None:
                self._validate_transition(
                    current.status,
                    next_status,
                )

            if (
                current_task_id is not None
                and current_task_id < 1
            ):
                raise ValueError(
                    "current_task_id must be positive."
                )

            updated = WorkflowRecord(
                workflow_id=current.workflow_id,
                user_id=current.user_id,
                goal=current.goal,
                plan_id=(
                    plan_id
                    if plan_id is not None
                    else current.plan_id
                ),
                status=next_status,
                current_task_id=(
                    None
                    if clear_current_task
                    else (
                        current_task_id
                        if current_task_id is not None
                        else current.current_task_id
                    )
                ),
                approval_fingerprint=(
                    None
                    if clear_approval
                    else (
                        approval_fingerprint
                        if approval_fingerprint is not None
                        else current.approval_fingerprint
                    )
                ),
                summary=(
                    summary.strip()
                    if summary is not None
                    and summary.strip()
                    else current.summary
                ),
                error=(
                    None
                    if clear_error
                    else (
                        error.strip()
                        if error is not None
                        and error.strip()
                        else current.error
                    )
                ),
                created_at=current.created_at,
                updated_at=self._now(),
            )

            data[workflow_id] = self._serialize(
                updated
            )

            self._write_data(data)

        return updated

    def list_for_user(
        self,
        user_id: int,
    ) -> list[WorkflowRecord]:
        if user_id < 1:
            raise ValueError("user_id must be positive.")

        with self._lock:
            data = self._read_data()

        records = [
            self._deserialize(raw_record)
            for raw_record in data.values()
            if isinstance(raw_record, dict)
            and raw_record.get("user_id") == user_id
        ]

        return sorted(
            records,
            key=lambda record: record.created_at,
        )

    def latest_for_user(
        self,
        user_id: int,
    ) -> WorkflowRecord | None:
        records = self.list_for_user(user_id)

        if not records:
            return None

        return records[-1]

    def progress(
        self,
        workflow_id: str,
    ) -> WorkflowProgress:
        record = self.require(workflow_id)

        return WorkflowProgress(
            workflow_id=record.workflow_id,
            goal=record.goal,
            status=record.status,
            plan_id=record.plan_id,
            current_task_id=record.current_task_id,
            approval_fingerprint=(
                record.approval_fingerprint
            ),
            summary=record.summary,
            error=record.error,
        )

    def delete(
        self,
        workflow_id: str,
    ) -> None:
        cleaned_workflow_id = workflow_id.strip()

        if not cleaned_workflow_id:
            raise ValueError(
                "workflow_id cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            data.pop(cleaned_workflow_id, None)
            self._write_data(data)

    @classmethod
    def _validate_transition(
        cls,
        current: WorkflowStatus,
        target: WorkflowStatus,
    ) -> None:
        if current == target:
            return

        allowed = cls.ALLOWED_TRANSITIONS[
            current
        ]

        if target not in allowed:
            raise WorkflowStateError(
                "Invalid workflow transition: "
                f"{current.value} -> {target.value}"
            )

    @staticmethod
    def _serialize(
        record: WorkflowRecord,
    ) -> dict[str, Any]:
        payload = asdict(record)
        payload["status"] = record.status.value
        return payload

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> WorkflowRecord:
        try:
            return WorkflowRecord(
                workflow_id=str(
                    payload["workflow_id"]
                ),
                user_id=int(payload["user_id"]),
                goal=str(payload["goal"]),
                plan_id=(
                    str(payload["plan_id"])
                    if payload.get("plan_id")
                    is not None
                    else None
                ),
                status=WorkflowStatus(
                    payload["status"]
                ),
                current_task_id=(
                    int(payload["current_task_id"])
                    if payload.get(
                        "current_task_id"
                    )
                    is not None
                    else None
                ),
                approval_fingerprint=(
                    str(
                        payload[
                            "approval_fingerprint"
                        ]
                    )
                    if payload.get(
                        "approval_fingerprint"
                    )
                    is not None
                    else None
                ),
                summary=str(
                    payload.get("summary", "")
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
            raise WorkflowStateError(
                "Stored workflow contains invalid data."
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
                raise WorkflowStateError(
                    "Workflow store must contain "
                    "a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise WorkflowStateError(
                "Workflow store contains invalid JSON."
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
    def _generate_workflow_id() -> str:
        return f"workflow-{uuid4().hex[:12]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()
