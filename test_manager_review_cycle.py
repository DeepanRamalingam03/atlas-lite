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
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1

        if self.calls == 1:
            return (
                "```python\n"
                "def add(a: int, b: int) -> int:\n"
                "    return a b\n"
                "```"
            )

        return (
            "```python\n"
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
            "```"
        )


class FakeOpenAIManager(BaseClient):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1

        assert "WORKER RESPONSE" in prompt

        return (
            "DECISION: APPROVED\n\n"
            "REASON:\n"
            "The corrected function is syntactically and logically valid.\n\n"
            "FIX_INSTRUCTION:\n"
            "NONE"
        )


test_root = Path(".atlas_manager_review_test")

if test_root.exists():
    shutil.rmtree(test_root)

gemini = FakeGeminiClient()
openai = FakeOpenAIManager()

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
    max_code_retries=2,
)

result = manager.ask(
    user_id=123,
    request="Create Python code for an add function.",
)

assert result.route.provider == "gemini"
assert result.iterations == 2
assert "return a + b" in result.answer
assert gemini.calls == 2
assert openai.calls == 1
assert "DECISION: APPROVED" in result.manager_review

shutil.rmtree(test_root)

print("OpenAI manager review cycle passed")
