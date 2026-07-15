from __future__ import annotations

from brain.context import ContextBuilder
from brain.planner import Planner
from brain.state import BrainState
from core.task import Task


class BrainManager:
    """Coordinates state, planning, context, and task lifecycle."""

    def __init__(
        self,
        state: BrainState | None = None,
        planner: Planner | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.state = state or BrainState()
        self.planner = planner or Planner()
        self.context_builder = context_builder or ContextBuilder()

    def prepare(self, task: Task) -> Task:
        """Register a task and return the next pending task."""
        self.state.add_task(task)
        self.state.conversation.add("user", task.prompt)

        next_task = self.planner.next_task(self.state)
        if next_task is None:
            raise RuntimeError("No pending task is available.")

        next_task.status = "running"
        self.state.iteration += 1
        return next_task

    def build_prompt(self, task: Task) -> str:
        """Build the worker prompt using current context."""
        context = self.context_builder.build(self.state).strip()

        if not context:
            return task.prompt

        return f"{context}\n\nCurrent task:\n{task.prompt}"

    def finalize(self, task: Task) -> Task:
        """Record a completed task and its response."""
        if task.result is None:
            raise RuntimeError("Cannot finalize a task without a result.")

        task.status = "completed"
        self.state.conversation.add("assistant", task.result)
        self.state.completed = True
        return task
