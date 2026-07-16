from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_file_reader import (
    ProjectFileReader,
)


test_root = Path(".atlas_project_file_reader_test")

if test_root.exists():
    shutil.rmtree(test_root)

(test_root / "core").mkdir(parents=True)
(test_root / "venv").mkdir(parents=True)

(test_root / "core" / "manager.py").write_text(
    "class Manager:\n"
    "    def run(self) -> str:\n"
    "        return 'ok'\n",
    encoding="utf-8",
)

(test_root / "README.md").write_text(
    "# Sample Project\n",
    encoding="utf-8",
)

(test_root / ".env").write_text(
    "SECRET=value\n",
    encoding="utf-8",
)

(test_root / "private.pem").write_text(
    "PRIVATE KEY\n",
    encoding="utf-8",
)

(test_root / "venv" / "ignored.py").write_text(
    "ignored = True\n",
    encoding="utf-8",
)

(test_root / "large.txt").write_text(
    "A" * 2_000,
    encoding="utf-8",
)

reader = ProjectFileReader(
    project_root=test_root,
    max_file_bytes=1_000,
)

manager_file = reader.read("core/manager.py")

assert manager_file.path == "core/manager.py"
assert "class Manager" in manager_file.content
assert manager_file.truncated is False
assert manager_file.size_bytes > 0

readme_file = reader.read("README.md")

assert "# Sample Project" in readme_file.content

large_file = reader.read("large.txt")

assert large_file.truncated is True
assert len(large_file.content) == 1_000
assert large_file.size_bytes == 2_000

many_files = reader.read_many(
    [
        "core/manager.py",
        "README.md",
    ]
)

assert len(many_files) == 2

try:
    reader.read("../outside.py")
except PermissionError:
    pass
else:
    raise AssertionError(
        "Path traversal must be blocked."
    )

try:
    reader.read(".env")
except PermissionError:
    pass
else:
    raise AssertionError(
        "Environment secrets must be blocked."
    )

try:
    reader.read("private.pem")
except PermissionError:
    pass
else:
    raise AssertionError(
        "Private key files must be blocked."
    )

try:
    reader.read("venv/ignored.py")
except PermissionError:
    pass
else:
    raise AssertionError(
        "Virtual environment files must be blocked."
    )

shutil.rmtree(test_root)

print("Project file reader passed")
