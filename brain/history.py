from __future__ import annotations

from core.message import Message


class ConversationHistory:

    def last(self, messages: list[Message], count: int = 10) -> list[Message]:
        return messages[-count:]

    def as_text(self, messages: list[Message]) -> str:
        return "\n".join(
            f"{message.role}: {message.content}"
            for message in messages
        )
