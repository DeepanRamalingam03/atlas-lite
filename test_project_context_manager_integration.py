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
from services.project.project_scanner import ProjectScanner


class FakeGeminiClient(BaseClient):
    def __init__(self) -> None:
        self.last_prompt = ""

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt

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
                "The implementation is valid and consistent "
                "with project knowledge.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return "Manager used the combined project knowledge."


test_root = Path(".atlas_context_manager_test")

if test_root.exists():
    shutil.rmtree(test_root)

openai = FakeOpenAIClient()
gemini = FakeGeminiClient()

manager = AtlasAssistantManager(
    clients={
        "openai": openai,
        "gemini": gemini,
    },
    router=IntentRouter(),
    memory=PersistentMemoryStore(
        storage_path=test_root / "memory.json",
        max_turns_per_user=6,
    ),
    code_validator=PythonCodeValidator(),
    constitution_loader=ConstitutionLoader(),
    project_scanner=ProjectScanner(),
    project_context_builder=ProjectContextBuilder(),
    project_root=".",
    max_code_retries=2,
)

assert "ATLAS CONSTITUTION" in manager.project_knowledge
assert "PROJECT FILE STRUCTURE" in manager.project_knowledge
assert "PYTHON PROJECT INDEX" in manager.project_knowledge
assert "AtlasAssistantManager" in manager.project_knowledge
assert "core/assistant_manager.py" in manager.project_knowledge

coding_result = manager.ask(
    user_id=501,
    request="Create Python code for an add function.",
)

assert "return a + b" in coding_result.answer
assert "ATLAS PROJECT KNOWLEDGE" in gemini.last_prompt
assert "PYTHON PROJECT INDEX" in gemini.last_prompt
assert "AtlasAssistantManager.ask" in gemini.last_prompt

planning_result = manager.ask(
    user_id=501,
    request="Plan the next architecture milestone.",
)

assert planning_result.route.provider == "openai"
assert "ATLAS PROJECT KNOWLEDGE" in openai.prompts[-1]
assert "PROJECT FILE STRUCTURE" in openai.prompts[-1]
assert "PYTHON PROJECT INDEX" in openai.prompts[-1]

shutil.rmtree(test_root)

print("Project context manager integration passed")
