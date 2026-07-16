from __future__ import annotations

import shutil
from pathlib import Path

from clients.base_client import BaseClient
from core.assistant_manager import AtlasAssistantManager
from core.intent_router import IntentRouter
from core.memory_store import PersistentMemoryStore
from services.code_validator import PythonCodeValidator


class FakeGeminiClient(BaseClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        return (
            "```python\n"
            "def add_numbers(a: int, b: int) -> int:\n"
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
                "The implementation is syntactically and logically valid.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return "OpenAI manager planning response."


test_root = Path(".atlas_manager_test")

if test_root.exists():
    shutil.rmtree(test_root)

openai_client = FakeOpenAIClient()
gemini_client = FakeGeminiClient()

manager = AtlasAssistantManager(
    clients={
        "openai": openai_client,
        "gemini": gemini_client,
    },
    router=IntentRouter(),
    memory=PersistentMemoryStore(
        storage_path=test_root / "memory.json",
        max_turns_per_user=6,
    ),
    code_validator=PythonCodeValidator(),
    max_code_retries=2,
)

coding_result = manager.ask(
    user_id=456,
    request="Create Python code for add_numbers.",
)

assert coding_result.route.provider == "gemini"
assert coding_result.iterations == 1
assert "return a + b" in coding_result.answer
assert "DECISION: APPROVED" in coding_result.manager_review
assert len(gemini_client.prompts) == 1
assert len(openai_client.prompts) == 1

planning_result = manager.ask(
    user_id=456,
    request="Plan the architecture for this project.",
)

assert planning_result.route.provider == "openai"
assert planning_result.answer == "OpenAI manager planning response."
assert planning_result.iterations == 1
assert len(openai_client.prompts) == 2
assert "Create Python code" in openai_client.prompts[1]
assert manager.history_size(456) == 4

manager.clear_memory(456)

assert manager.history_size(456) == 0

shutil.rmtree(test_root)

print("Atlas assistant manager passed")
