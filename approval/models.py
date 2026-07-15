from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True, frozen=True)
class ApprovalRequest:
    title: str
    message: str
    reference_id: str | None = None


@dataclass(slots=True, frozen=True)
class ApprovalResult:
    decision: ApprovalDecision
    response: str
    reference_id: str | None = None

    @property
    def approved(self) -> bool:
        return self.decision is ApprovalDecision.APPROVED
