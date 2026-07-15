from __future__ import annotations

from approval.console_gateway import ConsoleApprovalGateway
from approval.models import (
    ApprovalDecision,
    ApprovalRequest,
)
from approval.static_gateway import StaticApprovalGateway


request = ApprovalRequest(
    title="Atlas Release Approval",
    message="Apply two staged files and create a Git commit.",
    reference_id="release-001",
)

approved_static = StaticApprovalGateway(
    decision=ApprovalDecision.APPROVED,
)

approved_result = approved_static.request_approval(request)

assert approved_result.approved is True
assert approved_result.reference_id == "release-001"

rejected_static = StaticApprovalGateway(
    decision=ApprovalDecision.REJECTED,
)

rejected_result = rejected_static.request_approval(request)

assert rejected_result.approved is False


approved_inputs = iter(["invalid", "yes"])
approved_messages: list[str] = []

console_approved = ConsoleApprovalGateway(
    input_reader=lambda _: next(approved_inputs),
    output_writer=approved_messages.append,
    max_attempts=3,
)

console_approved_result = console_approved.request_approval(
    request
)

assert console_approved_result.approved is True
assert any(
    "Invalid response" in message
    for message in approved_messages
)


rejected_inputs = iter(["no"])

console_rejected = ConsoleApprovalGateway(
    input_reader=lambda _: next(rejected_inputs),
    output_writer=lambda _: None,
)

console_rejected_result = console_rejected.request_approval(
    request
)

assert console_rejected_result.approved is False


invalid_inputs = iter(["x", "x"])

console_invalid = ConsoleApprovalGateway(
    input_reader=lambda _: next(invalid_inputs),
    output_writer=lambda _: None,
    max_attempts=2,
)

console_invalid_result = console_invalid.request_approval(
    request
)

assert console_invalid_result.approved is False
assert (
    console_invalid_result.response
    == "Maximum approval attempts reached."
)

print("Approval gateway passed")
