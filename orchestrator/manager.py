from __future__ import annotations

from clients.base_client import BaseClient
from orchestrator.router import Router
from orchestrator.executor import Executor


class Orchestrator:

    def __init__(self, client: BaseClient):
        router = Router(client)
        self.executor = Executor(router)

    def execute(self, prompt: str) -> str:
        return self.executor.execute(prompt)

