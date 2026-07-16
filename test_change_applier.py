from __future__ import annotations

import shutil
from pathlib import Path

from core.execution.change_applier import (
    SafeChangeApplier,
)
from core.execution.change_approval import (
    ChangeDiffGenerator,
    HumanApprovalGate,
)
from core.execution.workspace import (
    SafeWorkspace,
)


test_root = Path(".atlas_change_applier_test")
project_root = test_root / "project"

if test_root.exists():
    shutil.rmtree(test_root)

(project_root / "core").mkdir(
    parents=True,
)

original_manager = (
    "class Manager:\n"
    "    pass\n"
)

(project_root / "core" / "manager.py").write_text(
    original_manager,
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

diff_generator = ChangeDiffGenerator(
    workspace=workspace,
)

approval_gate = HumanApprovalGate(
    storage_path=(
        test_root / "approvals.json"
    ),
)

applier = SafeChangeApplier(
    workspace=workspace,
    approval_gate=approval_gate,
    diff_generator=diff_generator,
)

unapproved_change_set = (
    diff_generator.generate()
)

try:
    applier.apply(
        unapproved_change_set
    )
except PermissionError:
    pass
else:
    raise AssertionError(
        "Unapproved changes must not be applied."
    )

assert (
    project_root
    / "core"
    / "manager.py"
).read_text(
    encoding="utf-8"
) == original_manager

assert (
    project_root
    / "services"
    / "new_service.py"
).exists() is False

approval_gate.request(
    unapproved_change_set
)

approval_gate.approve(
    unapproved_change_set.fingerprint,
    reason="Approved for apply test.",
)

workspace.write_text(
    "core/manager.py",
    (
        "class Manager:\n"
        "    def run(self) -> str:\n"
        "        return 'changed after approval'\n"
    ),
)

try:
    applier.apply(
        unapproved_change_set
    )
except PermissionError:
    pass
else:
    raise AssertionError(
        "Changed staging must invalidate approval."
    )

assert (
    project_root
    / "core"
    / "manager.py"
).read_text(
    encoding="utf-8"
) == original_manager

current_change_set = (
    diff_generator.generate()
)

approval_gate.request(
    current_change_set
)

approval_gate.approve(
    current_change_set.fingerprint,
    reason="Final approved change set.",
)

apply_result = applier.apply(
    approved_change_set=current_change_set,
    create_git_commit=False,
)

assert apply_result.fingerprint == (
    current_change_set.fingerprint
)

assert apply_result.applied_files == (
    "core/manager.py",
    "services/new_service.py",
)

assert apply_result.git_result is None

assert (
    project_root
    / "core"
    / "manager.py"
).read_text(
    encoding="utf-8"
) == (
    "class Manager:\n"
    "    def run(self) -> str:\n"
    "        return 'changed after approval'\n"
)

assert (
    project_root
    / "services"
    / "new_service.py"
).read_text(
    encoding="utf-8"
) == (
    "def execute() -> bool:\n"
    "    return True\n"
)

assert workspace.list_staged_files() == []

assert (
    project_root
    / ".atlas_apply_backup"
).exists() is False

workspace.write_text(
    "core/manager.py",
    (
        "class Manager:\n"
        "    def run(self) -> str:\n"
        "        return 'git test'\n"
    ),
)

git_change_set = (
    diff_generator.generate()
)

approval_gate.request(
    git_change_set
)

approval_gate.approve(
    git_change_set.fingerprint
)

try:
    applier.apply(
        approved_change_set=git_change_set,
        create_git_commit=True,
        commit_message="",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Git commit message must be required."
    )

assert workspace.list_staged_files() == [
    "core/manager.py",
]

shutil.rmtree(test_root)

print("Change applier passed")
