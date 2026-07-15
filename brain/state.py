from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.conversation import Conversation
from core.task import Task


@dataclass(slots=True)
class BrainState:
    """Mutable runtime state owned by the Atlas Lite brain."""

    conversation: Conversation = field(default_factory=Conversation)
    tasks: list[Task] = field(default_factory=list)
    current_provider: str = "gemini"
    iteration: int = 0
    approved: bool = False
    completed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)
