from __future__ import annotations

from dataclasses import dataclass

from approval.base_gateway import BaseApprovalGateway
from approval.models import ApprovalRequest, ApprovalResult
from release.coordinator import ReleaseCoordinator
from release.models import ReleaseResult


@dataclass(slots=True)
class ApprovedReleaseResult:
    success: bool
    approval_result: ApprovalResult
    release_result: ReleaseResult | None = None
    released: bool = False
    error: str | None = None


class ApprovalReleaseCoordinator:
    """
    Requests human approval before applying and committing staged changes.
    """

    def __init__(
        self,
        release_coordinator: ReleaseCoordinator,
        approval_gateway: BaseApprovalGateway,
    ) -> None:
        self.release_coordinator = release_coordinator
        self.approval_gateway = approval_gateway

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        reference_id: str | None = None,
    ) -> ApprovedReleaseResult:
        diff_plan = self.release_coordinator.preview()

        diff_summary = (
            self.release_coordinator.diff_engine.format_plan(
                diff_plan
            )
        )

        approval_request = ApprovalRequest(
            title="Atlas Lite Release Approval",
            message=(
                f"{diff_summary}\n\n"
                f"Commit message: {commit_message}\n"
                f"Push enabled: {push}"
            ),
            reference_id=reference_id,
        )

        approval_result = (
            self.approval_gateway.request_approval(
                approval_request
            )
        )

        if not approval_result.approved:
            return ApprovedReleaseResult(
                success=True,
                approval_result=approval_result,
                release_result=None,
                released=False,
                error=None,
            )

        release_result = self.release_coordinator.release(
            commit_message=commit_message,
            push=push,
            remote=remote,
            branch=branch,
            diff_plan=diff_plan,
        )

        if not release_result.success:
            return ApprovedReleaseResult(
                success=False,
                approval_result=approval_result,
                release_result=release_result,
                released=False,
                error=release_result.error,
            )

        return ApprovedReleaseResult(
            success=True,
            approval_result=approval_result,
            release_result=release_result,
            released=True,
            error=None,
        )
