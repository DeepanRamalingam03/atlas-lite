from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_indexer import ProjectIndexer


test_root = Path(".atlas_project_indexer_test")

if test_root.exists():
    shutil.rmtree(test_root)

package = test_root / "sample"
package.mkdir(parents=True)

(package / "__init__.py").write_text(
    "",
    encoding="utf-8",
)

(package / "worker.py").write_text(
    "from pathlib import Path\n"
    "import json\n\n"
    "class Worker:\n"
    "    def run(self) -> str:\n"
    "        return 'done'\n\n"
    "    async def stop(self) -> None:\n"
    "        return None\n\n"
    "def helper(value: int) -> int:\n"
    "    return value + 1\n",
    encoding="utf-8",
)

(package / "broken.py").write_text(
    "def broken(:\n"
    "    pass\n",
    encoding="utf-8",
)

excluded = test_root / "venv"
excluded.mkdir()

(excluded / "ignored.py").write_text(
    "def ignored():\n"
    "    return True\n",
    encoding="utf-8",
)

indexer = ProjectIndexer()

indexes = indexer.index_project(test_root)

paths = {
    item.path
    for item in indexes
}

assert "sample/worker.py" in paths
assert "sample/broken.py" in paths
assert "venv/ignored.py" not in paths

worker_index = next(
    item
    for item in indexes
    if item.path == "sample/worker.py"
)

symbol_names = {
    symbol.name
    for symbol in worker_index.symbols
}

assert "Worker" in symbol_names
assert "Worker.run" in symbol_names
assert "Worker.stop" in symbol_names
assert "helper" in symbol_names
assert worker_index.error is None

assert any(
    imported_module == "json"
    for imported_module in worker_index.imports
)

assert any(
    imported_module.startswith("pathlib:")
    for imported_module in worker_index.imports
)

broken_index = next(
    item
    for item in indexes
    if item.path == "sample/broken.py"
)

assert broken_index.error is not None
assert "SyntaxError" in broken_index.error

rendered = indexer.render(indexes)

assert "class: Worker" in rendered
assert "method: Worker.run" in rendered
assert "async_method: Worker.stop" in rendered
assert "function: helper" in rendered

shutil.rmtree(test_root)

print("Project indexer passed")
