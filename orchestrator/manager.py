from __future__ import annotations

from brain.manager import BrainManager
from core.task import Task
from orchestrator.executor import Executor


class Orchestrator:
    """Coordinates the Brain Manager and execution pipeline."""

    def __init__(
        self,
        brain: BrainManager,
        executor: Executor,
    ) -> None:
        self.brain = brain
        self.executor = executor

    def execute(self, task: Task) -> Task:
        """Execute one complete orchestration cycle."""
        active_task = self.brain.prepare(task)
        worker_prompt = self.brain.build_prompt(active_task)

        execution_task = Task(
            prompt=worker_prompt,
            provider=active_task.provider,
            metadata=dict(active_task.metadata),
        )

        executed_task = self.executor.execute(execution_task)

        active_task.result = executed_task.result
        return self.brain.finalize(active_task)
