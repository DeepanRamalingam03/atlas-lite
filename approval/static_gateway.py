from __future__ import annotations

from approval.base_gateway import BaseApprovalGateway
from approval.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResult,
)


class StaticApprovalGateway(BaseApprovalGateway):
    """
    Deterministic approval gateway used by tests and automation.
    """

    def __init__(
        self,
        decision: ApprovalDecision,
        response: str = "Static decision",
    ) -> None:
        self.decision = decision
        self.response = response

    def request_approval(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        return ApprovalResult(
            decision=self.decision,
            response=self.response,
            reference_id=request.reference_id,
        )
