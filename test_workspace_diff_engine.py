from __future__ import annotations

import shutil
from pathlib import Path

from workspace.diff_engine import (
    ChangeType,
    WorkspaceDiffEngine,
)


project_root = Path(".atlas_diff_project")
staging_root = Path(".atlas_diff_staging")

for root in (project_root, staging_root):
    if root.exists():
        shutil.rmtree(root)

    root.mkdir(parents=True)


(project_root / "unchanged.py").write_text(
    "VALUE = 1\n",
    encoding="utf-8",
)

(project_root / "modified.py").write_text(
    "VALUE = 1\n",
    encoding="utf-8",
)

(staging_root / "unchanged.py").write_text(
    "VALUE = 1\n",
    encoding="utf-8",
)

(staging_root / "modified.py").write_text(
    "VALUE = 2\n",
    encoding="utf-8",
)

(staging_root / "new_file.py").write_text(
    "VALUE = 3\n",
    encoding="utf-8",
)

cache_folder = staging_root / "__pycache__"
cache_folder.mkdir()

(cache_folder / "ignored.pyc").write_bytes(
    b"compiled-data"
)

engine = WorkspaceDiffEngine(
    project_root=project_root,
    staging_root=staging_root,
)

plan = engine.build_plan()

assert len(plan.files) == 3
assert len(plan.new_files) == 1
assert len(plan.modified_files) == 1
assert len(plan.unchanged_files) == 1
assert len(plan.actionable_files) == 2
assert plan.has_changes is True

changes_by_path = {
    item.relative_path: item.change_type
    for item in plan.files
}

assert changes_by_path["new_file.py"] is ChangeType.NEW
assert changes_by_path["modified.py"] is ChangeType.MODIFIED
assert (
    changes_by_path["unchanged.py"]
    is ChangeType.UNCHANGED
)

formatted = engine.format_plan(plan)

assert "+ NEW" in formatted
assert "* MODIFIED" in formatted
assert "= UNCHANGED" in formatted
assert "__pycache__" not in formatted
assert "Actionable: 2" in formatted

print(formatted)

shutil.rmtree(project_root)
shutil.rmtree(staging_root)

print("Workspace diff engine passed")
