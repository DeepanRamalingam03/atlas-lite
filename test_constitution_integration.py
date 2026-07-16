from __future__ import annotations

import shutil
from pathlib import Path

from clients.base_client import BaseClient
from core.assistant_manager import AtlasAssistantManager
from core.intent_router import IntentRouter
from core.memory_store import PersistentMemoryStore
from services.code_validator import PythonCodeValidator
from services.constitution_loader import ConstitutionLoader


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
                "The response is valid and follows the Constitution.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return "Manager response governed by the Constitution."


test_root = Path(".atlas_constitution_test")

if test_root.exists():
    shutil.rmtree(test_root)

gemini = FakeGeminiClient()
openai = FakeOpenAIClient()

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
    max_code_retries=2,
)

assert "Atlas AI Operating System" in manager.constitution
assert "Discord must remain an interface" in manager.constitution

coding_result = manager.ask(
    user_id=100,
    request="Create Python code for an add function.",
)

assert "return a + b" in coding_result.answer
assert "ATLAS CONSTITUTION" in gemini.last_prompt
assert "Atlas AI Operating System" in gemini.last_prompt
assert len(openai.prompts) == 1
assert "ATLAS CONSTITUTION" in openai.prompts[0]

planning_result = manager.ask(
    user_id=100,
    request="Plan the next project milestone.",
)

assert planning_result.route.provider == "openai"
assert len(openai.prompts) == 2
assert "ATLAS CONSTITUTION" in openai.prompts[1]
assert "Discord must remain an interface" in openai.prompts[1]

shutil.rmtree(test_root)

print("Constitution integration passed")
