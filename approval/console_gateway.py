from __future__ import annotations

from collections.abc import Callable

from approval.base_gateway import BaseApprovalGateway
from approval.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResult,
)


class ConsoleApprovalGateway(BaseApprovalGateway):
    """Requests approval using console input."""

    APPROVED_VALUES = {
        "y",
        "yes",
        "approve",
        "approved",
    }

    REJECTED_VALUES = {
        "n",
        "no",
        "reject",
        "rejected",
    }

    def __init__(
        self,
        input_reader: Callable[[str], str] = input,
        output_writer: Callable[[str], None] = print,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")

        self.input_reader = input_reader
        self.output_writer = output_writer
        self.max_attempts = max_attempts

    def request_approval(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        title = request.title.strip()
        message = request.message.strip()

        if not title:
            raise ValueError("Approval title cannot be empty.")

        if not message:
            raise ValueError("Approval message cannot be empty.")

        self.output_writer("")
        self.output_writer("=" * 72)
        self.output_writer(title)
        self.output_writer("=" * 72)
        self.output_writer(message)

        for _ in range(self.max_attempts):
            raw_response = self.input_reader(
                "Approve this operation? [yes/no]: "
            )

            normalized = raw_response.strip().lower()

            if normalized in self.APPROVED_VALUES:
                return ApprovalResult(
                    decision=ApprovalDecision.APPROVED,
                    response=raw_response.strip(),
                    reference_id=request.reference_id,
                )

            if normalized in self.REJECTED_VALUES:
                return ApprovalResult(
                    decision=ApprovalDecision.REJECTED,
                    response=raw_response.strip(),
                    reference_id=request.reference_id,
                )

            self.output_writer(
                "Invalid response. Enter yes or no."
            )

        return ApprovalResult(
            decision=ApprovalDecision.REJECTED,
            response="Maximum approval attempts reached.",
            reference_id=request.reference_id,
        )
