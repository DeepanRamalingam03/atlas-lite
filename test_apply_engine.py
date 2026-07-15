from __future__ import annotations

import shutil
from pathlib import Path

from apply.engine import TransactionalApplyEngine
from workspace.diff_engine import WorkspaceDiffEngine


project_root = Path(".atlas_apply_project")
staging_root = Path(".atlas_apply_staging")
backup_root = Path(".atlas_apply_backups")


def reset_directories() -> None:
    for root in (
        project_root,
        staging_root,
        backup_root,
    ):
        if root.exists():
            shutil.rmtree(root)

    project_root.mkdir(parents=True)
    staging_root.mkdir(parents=True)


reset_directories()

(project_root / "modified.py").write_text(
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

diff_engine = WorkspaceDiffEngine(
    project_root=project_root,
    staging_root=staging_root,
)

plan = diff_engine.build_plan()

apply_engine = TransactionalApplyEngine(
    project_root=project_root,
    staging_root=staging_root,
    backup_root=backup_root,
)

result = apply_engine.apply(plan)

assert result.success is True
assert result.rolled_back is False
assert len(result.applied_paths) == 2

assert (project_root / "modified.py").read_text(
    encoding="utf-8"
) == "VALUE = 2\n"

assert (project_root / "new_file.py").read_text(
    encoding="utf-8"
) == "VALUE = 3\n"

assert not backup_root.exists()


reset_directories()

(project_root / "a_success.py").write_text(
    "VALUE = 'old'\n",
    encoding="utf-8",
)

(project_root / "z_conflict").write_text(
    "This path is intentionally a file.\n",
    encoding="utf-8",
)

(staging_root / "a_success.py").write_text(
    "VALUE = 'new'\n",
    encoding="utf-8",
)

(staging_root / "z_conflict").mkdir()

(staging_root / "z_conflict" / "child.py").write_text(
    "VALUE = 99\n",
    encoding="utf-8",
)

failure_plan = WorkspaceDiffEngine(
    project_root=project_root,
    staging_root=staging_root,
).build_plan()

failure_result = TransactionalApplyEngine(
    project_root=project_root,
    staging_root=staging_root,
    backup_root=backup_root,
).apply(failure_plan)

assert failure_result.success is False
assert failure_result.rolled_back is True
assert failure_result.error is not None

assert (project_root / "a_success.py").read_text(
    encoding="utf-8"
) == "VALUE = 'old'\n"

assert (project_root / "z_conflict").is_file()
assert not backup_root.exists()

reset_directories()

print("Transactional apply engine passed")
