from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from apply.engine import TransactionalApplyEngine
from approval.models import ApprovalDecision
from approval.static_gateway import StaticApprovalGateway
from git_tools.engine import GitEngine
from release.approval_coordinator import (
    ApprovalReleaseCoordinator,
)
from release.coordinator import ReleaseCoordinator
from workspace.diff_engine import WorkspaceDiffEngine


project_root = Path(".atlas_approval_release_project")
staging_root = Path(".atlas_approval_release_staging")
backup_root = Path(".atlas_approval_release_backups")


def cleanup() -> None:
    for root in (
        project_root,
        staging_root,
        backup_root,
    ):
        if root.exists():
            shutil.rmtree(root)


def run_git(*args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stdout + result.stderr
        )


cleanup()

project_root.mkdir(parents=True)
staging_root.mkdir(parents=True)

run_git("init")
run_git("config", "user.name", "Atlas Test")
run_git(
    "config",
    "user.email",
    "atlas-test@example.com",
)

(project_root / "existing.py").write_text(
    "VALUE = 1\n",
    encoding="utf-8",
)

run_git("add", "existing.py")
run_git("commit", "-m", "Initial commit")

(staging_root / "existing.py").write_text(
    "VALUE = 2\n",
    encoding="utf-8",
)

(staging_root / "new_module.py").write_text(
    "ENABLED = True\n",
    encoding="utf-8",
)

git_engine = GitEngine(
    repository_root=project_root,
    timeout_seconds=30,
)

diff_engine = WorkspaceDiffEngine(
    project_root=project_root,
    staging_root=staging_root,
)

apply_engine = TransactionalApplyEngine(
    project_root=project_root,
    staging_root=staging_root,
    backup_root=backup_root,
)

release_coordinator = ReleaseCoordinator(
    project_root=project_root,
    staging_root=staging_root,
    git_engine=git_engine,
    apply_engine=apply_engine,
    diff_engine=diff_engine,
)

rejected_coordinator = ApprovalReleaseCoordinator(
    release_coordinator=release_coordinator,
    approval_gateway=StaticApprovalGateway(
        decision=ApprovalDecision.REJECTED,
        response="Rejected for test",
    ),
)

rejected_result = rejected_coordinator.release(
    commit_message="Rejected release",
    push=False,
    reference_id="release-rejected",
)

assert rejected_result.success is True
assert rejected_result.released is False
assert rejected_result.approval_result.approved is False

assert (project_root / "existing.py").read_text(
    encoding="utf-8"
) == "VALUE = 1\n"

assert not (project_root / "new_module.py").exists()

approved_coordinator = ApprovalReleaseCoordinator(
    release_coordinator=release_coordinator,
    approval_gateway=StaticApprovalGateway(
        decision=ApprovalDecision.APPROVED,
        response="Approved for test",
    ),
)

approved_result = approved_coordinator.release(
    commit_message="Approved Atlas release",
    push=False,
    reference_id="release-approved",
)

assert approved_result.success is True
assert approved_result.released is True
assert approved_result.approval_result.approved is True
assert approved_result.release_result is not None
assert approved_result.release_result.success is True

assert (project_root / "existing.py").read_text(
    encoding="utf-8"
) == "VALUE = 2\n"

assert (project_root / "new_module.py").read_text(
    encoding="utf-8"
) == "ENABLED = True\n"

status_result = git_engine.status()

assert status_result.success is True
assert status_result.stdout.strip() == ""

log_result = subprocess.run(
    [
        "git",
        "log",
        "-1",
        "--pretty=%s",
    ],
    cwd=project_root,
    capture_output=True,
    text=True,
    check=True,
)

assert log_result.stdout.strip() == (
    "Approved Atlas release"
)

cleanup()

print("Approval release coordinator passed")
