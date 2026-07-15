from __future__ import annotations

from brain.state import BrainState
from core.task import Task


class Planner:
    """Selects the next pending task from the current brain state."""

    def next_task(self, state: BrainState) -> Task | None:
        for task in state.tasks:
            if task.status == "pending":
                return task

        return None
