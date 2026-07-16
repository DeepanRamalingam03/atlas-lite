from __future__ import annotations

from core.assistant_manager import AtlasAssistantManager


class AtlasAssistant:
    """
    Interface adapter between communication gateways and Atlas Core.
    """

    def __init__(
        self,
        manager: AtlasAssistantManager,
    ) -> None:
        self.manager = manager

    def ask(
        self,
        user_id: int,
        question: str,
    ) -> str:
        result = self.manager.ask(
            user_id=user_id,
            request=question,
        )

        return result.answer

    def clear_history(self, user_id: int) -> None:
        self.manager.clear_memory(user_id)

    def history_size(self, user_id: int) -> int:
        return self.manager.history_size(user_id)
