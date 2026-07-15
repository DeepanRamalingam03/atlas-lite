from __future__ import annotations

from dataclasses import dataclass, field

from core.message import Message


@dataclass(slots=True)
class Conversation:
    """Stores the current in-memory conversation."""

    messages: list[Message] = field(default_factory=list)

    def add(self, role: str, content: str) -> Message:
        message = Message(role=role, content=content)
        self.messages.append(message)
        return message

    def clear(self) -> None:
        self.messages.clear()
