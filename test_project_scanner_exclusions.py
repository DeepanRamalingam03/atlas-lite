from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_scanner import ProjectScanner


test_root = Path(".atlas_scanner_exclusion_test")

if test_root.exists():
    shutil.rmtree(test_root)

(test_root / "core").mkdir(parents=True)
(test_root / "venv" / "lib").mkdir(parents=True)
(test_root / "__pycache__").mkdir(parents=True)
(test_root / ".atlas_data").mkdir(parents=True)

(test_root / "core" / "manager.py").write_text(
    "class Manager:\n"
    "    pass\n",
    encoding="utf-8",
)

(test_root / "venv" / "lib" / "ignored.py").write_text(
    "ignored = True\n",
    encoding="utf-8",
)

(test_root / "__pycache__" / "ignored.pyc").write_bytes(
    b"ignored"
)

(test_root / ".atlas_data" / "memory.json").write_text(
    "{}",
    encoding="utf-8",
)

(test_root / ".env").write_text(
    "SECRET=value\n",
    encoding="utf-8",
)

scanner = ProjectScanner()
result = scanner.scan(test_root)

assert "core/manager.py" in result
assert "venv/lib/ignored.py" not in result
assert "__pycache__" not in result
assert ".atlas_data" not in result
assert ".env" not in result

shutil.rmtree(test_root)

print("Project scanner exclusions passed")
