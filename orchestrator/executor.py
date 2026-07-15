from __future__ import annotations

from orchestrator.router import Router
from core.task import Task


class Executor:
    """
    Executes a task using the selected worker.
    """

    def __init__(self, router: Router):
        self.router = router

    def execute(self, task: Task) -> Task:

        client = self.router.route()

        task.result = client.generate(task.prompt)

        task.status = "completed"

        return task
