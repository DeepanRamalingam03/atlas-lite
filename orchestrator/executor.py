from __future__ import annotations

from orchestrator.router import Router


class Executor:

    def __init__(self, router: Router):
        self.router = router

    def execute(self, prompt: str) -> str:
        client = self.router.route()
        return client.generate(prompt)
