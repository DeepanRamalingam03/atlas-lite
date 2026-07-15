from __future__ import annotations

from abc import ABC, abstractmethod

from approval.models import ApprovalRequest, ApprovalResult


class BaseApprovalGateway(ABC):
    """Common interface for console, WhatsApp, and API approval gateways."""

    @abstractmethod
    def request_approval(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        """Request and return a human approval decision."""
        raise NotImplementedError
