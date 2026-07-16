from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_context_builder import (
    ProjectContextBuilder,
)


test_root = Path(".atlas_project_context_test")

if test_root.exists():
    shutil.rmtree(test_root)

package = test_root / "sample"
package.mkdir(parents=True)

(package / "__init__.py").write_text(
    "",
    encoding="utf-8",
)

(package / "service.py").write_text(
    "from pathlib import Path\n\n"
    "class SampleService:\n"
    "    def run(self, value: int) -> int:\n"
    "        return value + 1\n\n"
    "def helper() -> str:\n"
    "    return 'ok'\n",
    encoding="utf-8",
)

builder = ProjectContextBuilder(
    max_context_characters=120_000,
)

context = builder.build(test_root)

assert "ATLAS CONSTITUTION" in context
assert "Atlas AI Operating System" in context

assert "PROJECT FILE STRUCTURE" in context
assert "sample/service.py" in context

assert "PYTHON PROJECT INDEX" in context
assert "class: SampleService" in context
assert "method: SampleService.run" in context
assert "function: helper" in context
assert "pathlib:" in context

shutil.rmtree(test_root)

print("Project context builder passed")
