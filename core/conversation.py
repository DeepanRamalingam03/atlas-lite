from __future__ import annotations

from dataclasses import dataclass, field

from core.message import Message


@dataclass(slots=True)
class Conversation:
    messages: list[Message] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def clear(self) -> None:
        self.messages.clear()
