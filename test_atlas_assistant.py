from __future__ import annotations

import unittest
from dataclasses import dataclass

from assistants.service import AtlasAssistant


@dataclass(slots=True, frozen=True)
class FakeManagerResponse:
    answer: str


class FakeAssistantManager:
    def __init__(self) -> None:
        self.history: dict[int, list[str]] = {}

    def ask(
        self,
        user_id: int,
        request: str,
    ) -> FakeManagerResponse:
        cleaned_request = request.strip()

        if not cleaned_request:
            raise ValueError(
                "Request cannot be empty."
            )

        user_history = self.history.setdefault(
            user_id,
            [],
        )

        if cleaned_request == "second question":
            if "first question" not in user_history:
                raise AssertionError(
                    "Previous user request was not retained."
                )

        user_history.extend(
            [
                cleaned_request,
                "Atlas test response",
            ]
        )

        return FakeManagerResponse(
            answer="Atlas test response"
        )

    def clear_memory(
        self,
        user_id: int,
    ) -> None:
        self.history.pop(
            user_id,
            None,
        )

    def history_size(
        self,
        user_id: int,
    ) -> int:
        return len(
            self.history.get(
                user_id,
                [],
            )
        )


class AtlasAssistantTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.manager = FakeAssistantManager()

        self.assistant = AtlasAssistant(
            manager=self.manager,
        )

    def test_ask_returns_manager_answer(
        self,
    ) -> None:
        response = self.assistant.ask(
            user_id=123,
            question="first question",
        )

        self.assertEqual(
            response,
            "Atlas test response",
        )

        self.assertEqual(
            self.assistant.history_size(
                123
            ),
            2,
        )

    def test_previous_history_is_available(
        self,
    ) -> None:
        self.assistant.ask(
            user_id=123,
            question="first question",
        )

        response = self.assistant.ask(
            user_id=123,
            question="second question",
        )

        self.assertEqual(
            response,
            "Atlas test response",
        )

        self.assertEqual(
            self.assistant.history_size(
                123
            ),
            4,
        )

    def test_clear_history(
        self,
    ) -> None:
        self.assistant.ask(
            user_id=123,
            question="first question",
        )

        self.assistant.clear_history(
            123
        )

        self.assertEqual(
            self.assistant.history_size(
                123
            ),
            0,
        )

    def test_multiple_users_are_isolated(
        self,
    ) -> None:
        self.assistant.ask(
            user_id=100,
            question="first question",
        )

        self.assistant.ask(
            user_id=200,
            question="another question",
        )

        self.assertEqual(
            self.assistant.history_size(
                100
            ),
            2,
        )

        self.assertEqual(
            self.assistant.history_size(
                200
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
