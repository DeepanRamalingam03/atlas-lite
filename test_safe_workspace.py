from __future__ import annotations

import shutil
from pathlib import Path

from core.execution.workspace import (
    SafeWorkspace,
    WorkspaceSecurityError,
)


test_root = Path(".atlas_safe_workspace_test")
project_root = test_root / "project"

if test_root.exists():
    shutil.rmtree(test_root)

(project_root / "core").mkdir(
    parents=True,
)

(project_root / "venv").mkdir(
    parents=True,
)

(project_root / "core" / "manager.py").write_text(
    "class Manager:\n"
    "    pass\n",
    encoding="utf-8",
)

(project_root / ".env").write_text(
    "SECRET=value\n",
    encoding="utf-8",
)

(project_root / "private.pem").write_text(
    "PRIVATE KEY\n",
    encoding="utf-8",
)

(project_root / "venv" / "ignored.py").write_text(
    "ignored = True\n",
    encoding="utf-8",
)

workspace = SafeWorkspace(
    project_root=project_root,
    staging_root=".atlas_staging",
    max_file_bytes=10_000,
)

workspace.prepare()

assert workspace.list_staged_files() == []

staged_existing = workspace.stage_existing_file(
    "core/manager.py"
)

assert staged_existing.exists()
assert (
    staged_existing.read_text(encoding="utf-8")
    == "class Manager:\n    pass\n"
)

change = workspace.write_text(
    "core/manager.py",
    (
        "class Manager:\n"
        "    def run(self) -> str:\n"
        "        return 'ok'\n"
    ),
)

assert change.relative_path == "core/manager.py"
assert change.original_exists is True
assert change.original_hash is not None
assert len(change.original_hash) == 64
assert len(change.staged_hash) == 64
assert change.original_hash != change.staged_hash

assert "def run" in workspace.read_staged(
    "core/manager.py"
)

new_change = workspace.write_text(
    "services/new_service.py",
    (
        "def execute() -> bool:\n"
        "    return True\n"
    ),
)

assert new_change.original_exists is False
assert new_change.original_hash is None

assert workspace.list_staged_files() == [
    "core/manager.py",
    "services/new_service.py",
]

assert (
    project_root
    / "services"
    / "new_service.py"
).exists() is False

assert (
    project_root
    / "core"
    / "manager.py"
).read_text(
    encoding="utf-8"
) == "class Manager:\n    pass\n"

try:
    workspace.write_text(
        "../outside.py",
        "blocked = True\n",
    )
except WorkspaceSecurityError:
    pass
else:
    raise AssertionError(
        "Path traversal must be blocked."
    )

try:
    workspace.write_text(
        ".env",
        "SECRET=changed\n",
    )
except WorkspaceSecurityError:
    pass
else:
    raise AssertionError(
        "Environment files must be blocked."
    )

try:
    workspace.write_text(
        "private.pem",
        "PRIVATE KEY\n",
    )
except WorkspaceSecurityError:
    pass
else:
    raise AssertionError(
        "Private keys must be blocked."
    )

try:
    workspace.write_text(
        "venv/ignored.py",
        "ignored = False\n",
    )
except WorkspaceSecurityError:
    pass
else:
    raise AssertionError(
        "Virtual environment files must be blocked."
    )

workspace.discard()

assert workspace.list_staged_files() == []

shutil.rmtree(test_root)

print("Safe workspace passed")
