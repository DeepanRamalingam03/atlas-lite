from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLYING = "applying"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True, frozen=True)
class WorkflowRecord:
    workflow_id: str
    user_id: int
    goal: str
    plan_id: str | None
    status: WorkflowStatus
    current_task_id: int | None
    approval_fingerprint: str | None
    summary: str
    error: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class WorkflowProgress:
    workflow_id: str
    goal: str
    status: WorkflowStatus
    plan_id: str | None
    current_task_id: int | None
    approval_fingerprint: str | None
    summary: str
    error: str | None

    @property
    def waiting_for_human(self) -> bool:
        return self.status == WorkflowStatus.WAITING_APPROVAL

    @property
    def finished(self) -> bool:
        return self.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.STOPPED,
        }
