from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_memory import (
    ProjectMemory,
)


test_root = Path(".atlas_project_memory_test")
storage_path = test_root / "memory.json"
project_root = test_root / "sample_project"

if test_root.exists():
    shutil.rmtree(test_root)

project_root.mkdir(parents=True)

memory = ProjectMemory(
    storage_path=storage_path,
)

assert memory.load(project_root) is None

context_v1 = (
    "PROJECT FILE STRUCTURE\n"
    "core/manager.py\n\n"
    "PYTHON PROJECT INDEX\n"
    "class: Manager"
)

snapshot_v1 = memory.save(
    project_root=project_root,
    context=context_v1,
)

assert snapshot_v1.project_root == str(
    project_root.resolve()
)
assert len(snapshot_v1.fingerprint) == 64
assert snapshot_v1.context == context_v1
assert snapshot_v1.created_at

loaded_v1 = memory.load(project_root)

assert loaded_v1 is not None
assert loaded_v1 == snapshot_v1

assert memory.is_current(
    project_root=project_root,
    context=context_v1,
) is True

context_v2 = (
    context_v1
    + "\nfunction: build"
)

assert memory.is_current(
    project_root=project_root,
    context=context_v2,
) is False

snapshot_v2 = memory.save(
    project_root=project_root,
    context=context_v2,
)

assert snapshot_v2.fingerprint != (
    snapshot_v1.fingerprint
)
assert memory.is_current(
    project_root=project_root,
    context=context_v2,
) is True

reloaded_memory = ProjectMemory(
    storage_path=storage_path,
)

reloaded_snapshot = reloaded_memory.load(
    project_root
)

assert reloaded_snapshot == snapshot_v2

reloaded_memory.clear(project_root)

assert reloaded_memory.load(
    project_root
) is None

shutil.rmtree(test_root)

print("Project memory passed")
