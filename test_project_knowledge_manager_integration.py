from __future__ import annotations

import shutil
from pathlib import Path

from clients.base_client import BaseClient
from core.assistant_manager import AtlasAssistantManager
from core.intent_router import IntentRouter
from core.memory_store import PersistentMemoryStore
from services.code_validator import PythonCodeValidator
from services.constitution_loader import ConstitutionLoader
from services.project.project_context_builder import (
    ProjectContextBuilder,
)
from services.project.project_knowledge_service import (
    ProjectKnowledgeService,
)
from services.project.project_memory import ProjectMemory
from services.project.project_scanner import ProjectScanner


class FakeGeminiClient(BaseClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        return (
            "```python\n"
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
            "```"
        )


class FakeOpenAIClient(BaseClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        if "WORKER RESPONSE" in prompt:
            return (
                "DECISION: APPROVED\n\n"
                "REASON:\n"
                "The implementation is valid and matches "
                "the project knowledge.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return "Manager response using refreshed project knowledge."


test_root = Path(".atlas_knowledge_manager_test")
project_root = test_root / "sample_project"
memory_path = test_root / "project_memory.json"
conversation_path = test_root / "conversation_memory.json"

if test_root.exists():
    shutil.rmtree(test_root)

project_root.mkdir(parents=True)

(project_root / "service.py").write_text(
    "class Service:\n"
    "    def run(self) -> str:\n"
    "        return 'v1'\n",
    encoding="utf-8",
)

constitution_loader = ConstitutionLoader()
scanner = ProjectScanner()

context_builder = ProjectContextBuilder(
    constitution_loader=constitution_loader,
    scanner=scanner,
)

knowledge_service = ProjectKnowledgeService(
    context_builder=context_builder,
    memory=ProjectMemory(
        storage_path=memory_path,
    ),
)

openai = FakeOpenAIClient()
gemini = FakeGeminiClient()

manager = AtlasAssistantManager(
    clients={
        "openai": openai,
        "gemini": gemini,
    },
    router=IntentRouter(),
    memory=PersistentMemoryStore(
        storage_path=conversation_path,
        max_turns_per_user=6,
    ),
    code_validator=PythonCodeValidator(),
    constitution_loader=constitution_loader,
    project_scanner=scanner,
    project_context_builder=context_builder,
    project_knowledge_service=knowledge_service,
    project_root=project_root,
    max_code_retries=2,
)

first_fingerprint = manager.project_knowledge_fingerprint

assert len(first_fingerprint) == 64
assert manager.project_knowledge_changed is True
assert "class: Service" in manager.project_knowledge
assert "method: Service.run" in manager.project_knowledge

coding_result = manager.ask(
    user_id=700,
    request="Create Python code for an add function.",
)

assert "return a + b" in coding_result.answer
assert manager.project_knowledge_changed is False
assert "Knowledge fingerprint:" in gemini.prompts[-1]
assert first_fingerprint in gemini.prompts[-1]

(project_root / "service.py").write_text(
    "class Service:\n"
    "    def run(self) -> str:\n"
    "        return 'v2'\n\n"
    "def helper() -> bool:\n"
    "    return True\n",
    encoding="utf-8",
)

planning_result = manager.ask(
    user_id=700,
    request="Plan the next architecture milestone.",
)

assert planning_result.route.provider == "openai"
assert manager.project_knowledge_changed is True
assert (
    manager.project_knowledge_fingerprint
    != first_fingerprint
)
assert "function: helper" in manager.project_knowledge
assert "function: helper" in openai.prompts[-1]
assert "Knowledge changed during last refresh: True" in (
    openai.prompts[-1]
)

shutil.rmtree(test_root)

print("Project knowledge manager integration passed")
