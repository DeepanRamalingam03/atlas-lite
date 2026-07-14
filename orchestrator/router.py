from __future__ import annotations

from clients.base_client import BaseClient


class Router:

    def __init__(self, client: BaseClient):
        self.client = client

    def route(self) -> BaseClient:
        return self.client
