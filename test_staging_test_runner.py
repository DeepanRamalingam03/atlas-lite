from __future__ import annotations

from pathlib import Path

from core.file_change import FileChange
from testing.runner import StagingTestRunner
from workspace.writer import WorkspaceWriter


staging_root = Path(".atlas_test_staging")

writer = WorkspaceWriter(staging_root=staging_root)

runner = StagingTestRunner(
    staging_root=staging_root,
    timeout_seconds=30,
)

writer.clear()

writer.write_changes(
    [
        FileChange(
            path="valid_module.py",
            content=(
                "def add_numbers(a: int, b: int) -> int:\n"
                "    return a + b\n"
            ),
        )
    ]
)

valid_result = runner.run_compile_check()

assert valid_result.success is True
assert valid_result.return_code == 0

writer.clear()

writer.write_changes(
    [
        FileChange(
            path="invalid_module.py",
            content=(
                "def broken_function(\n"
                "    return True\n"
            ),
        )
    ]
)

invalid_result = runner.run_compile_check()

assert invalid_result.success is False
assert invalid_result.return_code != 0
assert "SyntaxError" in invalid_result.combined_output

writer.clear()
staging_root.rmdir()

print("Staging test runner passed")
