from __future__ import annotations

import unittest
from unittest.mock import patch

from clients.base_client import BaseClient
from run_continuous_runtime import build_pipeline
from workers.fallback_worker import FallbackWorker


class FakeClient(BaseClient):
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def generate(self, prompt: str) -> str:
        return '{"summary":"ok","files":[]}'


class RuntimeOpenAIOnlyWorkerTest(unittest.TestCase):
    def test_production_worker_uses_only_openai(self) -> None:
        created: list[str] = []

        def create(provider: str) -> FakeClient:
            created.append(provider)
            return FakeClient(provider)

        with patch(
            "run_continuous_runtime.ClientFactory.create",
            side_effect=create,
        ):
            pipeline = build_pipeline()

        self.assertIsInstance(
            pipeline.worker,
            FallbackWorker,
        )

        self.assertEqual(
            [
                provider
                for provider, _
                in pipeline.worker.workers
            ],
            ["openai"],
        )

        # OpenAI is used separately for manager and worker.
        self.assertGreaterEqual(
            created.count("openai"),
            2,
        )

        self.assertNotIn(
            "gemini",
            created,
        )


if __name__ == "__main__":
    unittest.main()
