from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock

from clients.base_client import BaseClient


@dataclass(slots=True)
class ConversationTurn:
    role: str
    content: str


@dataclass(slots=True)
class AtlasAssistant:
    """
    Conversational AI service used by Discord.

    OpenAI currently acts as the Atlas conversational manager.
    Short per-user history is retained in memory while the process runs.
    """

    manager_client: BaseClient
    max_history_turns: int = 8

    _history: dict[int, deque[ConversationTurn]] = field(
        init=False,
        default_factory=lambda: defaultdict(deque),
    )
    _lock: Lock = field(
        init=False,
        default_factory=Lock,
    )

    def __post_init__(self) -> None:
        if self.max_history_turns < 1:
            raise ValueError(
                "max_history_turns must be at least 1."
            )

    def ask(
        self,
        user_id: int,
        question: str,
    ) -> str:
        cleaned_question = question.strip()

        if not cleaned_question:
            raise ValueError("Question cannot be empty.")

        prompt = self._build_prompt(
            user_id=user_id,
            question=cleaned_question,
        )

        response = self.manager_client.generate(prompt).strip()

        if not response:
            response = (
                "Atlas did not receive a usable response "
                "from the manager model."
            )

        with self._lock:
            history = self._history[user_id]

            history.append(
                ConversationTurn(
                    role="USER",
                    content=cleaned_question,
                )
            )

            history.append(
                ConversationTurn(
                    role="ATLAS",
                    content=response,
                )
            )

            while len(history) > self.max_history_turns:
                history.popleft()

        return response

    def clear_history(self, user_id: int) -> None:
        with self._lock:
            self._history.pop(user_id, None)

    def history_size(self, user_id: int) -> int:
        with self._lock:
            return len(self._history.get(user_id, ()))

    def _build_prompt(
        self,
        user_id: int,
        question: str,
    ) -> str:
        with self._lock:
            history_snapshot = list(
                self._history.get(user_id, ())
            )

        history_text = "\n".join(
            f"{turn.role}: {turn.content}"
            for turn in history_snapshot
        )

        if not history_text:
            history_text = "No previous conversation."

        return (
            "You are Atlas Lite, an AI project manager and technical "
            "assistant.\n\n"
            "Your responsibilities:\n"
            "- Understand the user's request clearly.\n"
            "- Give practical and accurate answers.\n"
            "- For coding questions, provide complete usable guidance.\n"
            "- Do not claim that a command, trade, deployment, or file "
            "change was executed unless it actually was.\n"
            "- Keep responses suitable for Discord.\n"
            "- Avoid unnecessary introductions and repetition.\n\n"
            "CONVERSATION HISTORY\n"
            "====================\n"
            f"{history_text}\n\n"
            "CURRENT USER REQUEST\n"
            "====================\n"
            f"{question}\n\n"
            "Respond directly to the current request."
        )
