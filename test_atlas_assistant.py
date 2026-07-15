from __future__ import annotations

from clients.base_client import BaseClient
from assistants.service import AtlasAssistant


class FakeManagerClient(BaseClient):
    def generate(self, prompt: str) -> str:
        assert "CURRENT USER REQUEST" in prompt

        if "second question" in prompt:
            assert "first question" in prompt

        return "Atlas test response"


assistant = AtlasAssistant(
    manager_client=FakeManagerClient(),
    max_history_turns=4,
)

first_response = assistant.ask(
    user_id=123,
    question="first question",
)

assert first_response == "Atlas test response"
assert assistant.history_size(123) == 2

second_response = assistant.ask(
    user_id=123,
    question="second question",
)

assert second_response == "Atlas test response"
assert assistant.history_size(123) == 4

assistant.clear_history(123)

assert assistant.history_size(123) == 0

print("Atlas assistant passed")
