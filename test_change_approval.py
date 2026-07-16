from __future__ import annotations

import shutil
from pathlib import Path

from core.execution.change_approval import (
    ApprovalStatus,
    ChangeDiffGenerator,
    HumanApprovalGate,
)
from core.execution.workspace import SafeWorkspace


test_root = Path(".atlas_change_approval_test")
project_root = test_root / "project"

if test_root.exists():
    shutil.rmtree(test_root)

(project_root / "core").mkdir(
    parents=True,
)

(project_root / "core" / "manager.py").write_text(
    "class Manager:\n"
    "    pass\n",
    encoding="utf-8",
)

workspace = SafeWorkspace(
    project_root=project_root,
    staging_root=".atlas_staging",
)

workspace.prepare()

workspace.write_text(
    "core/manager.py",
    (
        "class Manager:\n"
        "    def run(self) -> str:\n"
        "        return 'ok'\n"
    ),
)

workspace.write_text(
    "services/new_service.py",
    (
        "def execute() -> bool:\n"
        "    return True\n"
    ),
)

generator = ChangeDiffGenerator(
    workspace=workspace,
)

change_set = generator.generate()

assert len(change_set.files) == 2
assert len(change_set.fingerprint) == 64

assert "a/core/manager.py" in (
    change_set.rendered_diff
)
assert "b/core/manager.py" in (
    change_set.rendered_diff
)
assert "+    def run(self) -> str:" in (
    change_set.rendered_diff
)

assert "/dev/null" in (
    change_set.rendered_diff
)
assert "b/services/new_service.py" in (
    change_set.rendered_diff
)

gate = HumanApprovalGate(
    storage_path=(
        test_root / "approvals.json"
    ),
)

request_record = gate.request(
    change_set
)

assert request_record.status == (
    ApprovalStatus.PENDING
)
assert request_record.decided_at is None

try:
    gate.require_approved(change_set)
except PermissionError:
    pass
else:
    raise AssertionError(
        "Pending change sets must not be accepted."
    )

approved_record = gate.approve(
    fingerprint=change_set.fingerprint,
    reason="Reviewed and approved.",
)

assert approved_record.status == (
    ApprovalStatus.APPROVED
)
assert approved_record.reason == (
    "Reviewed and approved."
)
assert approved_record.decided_at is not None

required_record = gate.require_approved(
    change_set
)

assert required_record.status == (
    ApprovalStatus.APPROVED
)

workspace.write_text(
    "core/manager.py",
    (
        "class Manager:\n"
        "    def run(self) -> str:\n"
        "        return 'changed again'\n"
    ),
)

changed_change_set = generator.generate()

assert (
    changed_change_set.fingerprint
    != change_set.fingerprint
)

try:
    gate.require_approved(
        changed_change_set
    )
except PermissionError:
    pass
else:
    raise AssertionError(
        "Modified staged changes require new approval."
    )

rejection_request = gate.request(
    changed_change_set
)

assert rejection_request.status == (
    ApprovalStatus.PENDING
)

rejected_record = gate.reject(
    fingerprint=(
        changed_change_set.fingerprint
    ),
    reason="Changes need correction.",
)

assert rejected_record.status == (
    ApprovalStatus.REJECTED
)

try:
    gate.require_approved(
        changed_change_set
    )
except PermissionError:
    pass
else:
    raise AssertionError(
        "Rejected change sets must remain blocked."
    )

try:
    gate.approve(
        changed_change_set.fingerprint
    )
except RuntimeError:
    pass
else:
    raise AssertionError(
        "A decided request cannot be approved again."
    )

workspace.discard()

try:
    generator.generate()
except ValueError:
    pass
else:
    raise AssertionError(
        "Empty staging workspaces must be rejected."
    )

shutil.rmtree(test_root)

print("Change approval gate passed")
