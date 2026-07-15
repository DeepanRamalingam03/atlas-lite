from __future__ import annotations

from pathlib import Path

from core.file_change import FileChange
from workspace.writer import WorkspaceWriter


staging_root = Path(".atlas_test_staging")
writer = WorkspaceWriter(staging_root=staging_root)

writer.clear()

changes = [
    FileChange(
        path="sample.py",
        content="def hello():\n    return 'hello'\n",
    ),
    FileChange(
        path="nested/example.py",
        content="VALUE = 42\n",
    ),
]

written_paths = writer.write_changes(changes)

assert len(written_paths) == 2
assert (staging_root / "sample.py").read_text(
    encoding="utf-8"
) == "def hello():\n    return 'hello'\n"
assert (staging_root / "nested/example.py").read_text(
    encoding="utf-8"
) == "VALUE = 42\n"

try:
    writer.write_changes(
        [
            FileChange(
                path="../unsafe.py",
                content="bad = True\n",
            )
        ]
    )
except ValueError:
    pass
else:
    raise AssertionError("Unsafe path was not rejected.")

writer.clear()
staging_root.rmdir()

print("Workspace writer passed")
