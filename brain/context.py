from __future__ import annotations

from brain.history import ConversationHistory
from brain.state import BrainState


class ContextBuilder:

    def __init__(self):
        self.history = ConversationHistory()

    def build(self, state: BrainState) -> str:
        recent = self.history.last(state.conversation.messages)
        return self.history.as_text(recent)
