from __future__ import annotations

from clients.base_client import BaseClient


class Router:
    """
    Responsible for selecting the execution provider.

    Current Version
    ---------------
    Always returns the configured worker.

    Future
    ------
    Will support:

    - Gemini
    - OpenAI
    - Claude
    """

    def __init__(self, client: BaseClient):
        self.client = client

    def route(self, provider: str | None = None) -> BaseClient:
        return self.client
