from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_context_builder import (
    ProjectContextBuilder,
)
from services.project.project_knowledge_service import (
    ProjectKnowledgeService,
)
from services.project.project_memory import ProjectMemory


test_root = Path(".atlas_project_knowledge_test")
project_root = test_root / "sample_project"
storage_path = test_root / "project_memory.json"

if test_root.exists():
    shutil.rmtree(test_root)

project_root.mkdir(parents=True)

(project_root / "service.py").write_text(
    "class Service:\n"
    "    def run(self) -> str:\n"
    "        return 'v1'\n",
    encoding="utf-8",
)

service = ProjectKnowledgeService(
    context_builder=ProjectContextBuilder(),
    memory=ProjectMemory(
        storage_path=storage_path,
    ),
)

first_result = service.refresh(project_root)

assert first_result.changed is True
assert len(first_result.fingerprint) == 64
assert "service.py" in first_result.context
assert "class: Service" in first_result.context
assert "method: Service.run" in first_result.context
assert "Atlas AI Operating System" in first_result.context

second_result = service.refresh(project_root)

assert second_result.changed is False
assert second_result.fingerprint == first_result.fingerprint
assert second_result.context == first_result.context

loaded_result = service.load(project_root)

assert loaded_result is not None
assert loaded_result.changed is False
assert loaded_result.fingerprint == first_result.fingerprint

(project_root / "service.py").write_text(
    "class Service:\n"
    "    def run(self) -> str:\n"
    "        return 'v2'\n\n"
    "def helper() -> bool:\n"
    "    return True\n",
    encoding="utf-8",
)

third_result = service.refresh(project_root)

assert third_result.changed is True
assert third_result.fingerprint != first_result.fingerprint
assert "function: helper" in third_result.context

service.clear(project_root)

assert service.load(project_root) is None

refreshed_result = service.get_or_refresh(project_root)

assert refreshed_result.changed is True
assert "function: helper" in refreshed_result.context

shutil.rmtree(test_root)

print("Project knowledge service passed")
