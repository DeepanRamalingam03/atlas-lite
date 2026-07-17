from __future__ import annotations

import unittest
from unittest.mock import patch

from clients.base_client import BaseClient
from run_continuous_runtime import (
    build_pipeline,
)
from workers.fallback_worker import (
    FallbackWorker,
)


class FakeClient(BaseClient):
    def __init__(
        self,
        provider: str,
    ) -> None:
        self.provider = provider
        self.prompts: list[str] = []

    def generate(
        self,
        prompt: str,
    ) -> str:
        self.prompts.append(prompt)

        return (
            '{"summary":"ok","files":[]}'
        )


class RuntimeWorkerFailoverTest(
    unittest.TestCase
):
    def test_production_pipeline_has_ordered_failover(
        self,
    ) -> None:
        clients: dict[
            str,
            FakeClient,
        ] = {}

        def create_client(
            provider: str,
        ) -> FakeClient:
            client = FakeClient(provider)
            clients[provider] = client
            return client

        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            side_effect=create_client,
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
            [
                "gemini",
                "openai",
            ],
        )

        self.assertIn(
            "gemini",
            clients,
        )

        self.assertIn(
            "openai",
            clients,
        )

    def test_production_fallback_uses_openai(
        self,
    ) -> None:
        class FailingGemini(
            BaseClient
        ):
            def generate(
                self,
                prompt: str,
            ) -> str:
                raise RuntimeError(
                    "504 DEADLINE_EXCEEDED"
                )

        class WorkingOpenAI(
            BaseClient
        ):
            def generate(
                self,
                prompt: str,
            ) -> str:
                return (
                    '{"summary":"openai fallback",'
                    '"files":[]}'
                )

        def create_client(
            provider: str,
        ) -> BaseClient:
            if provider == "gemini":
                return FailingGemini()

            return WorkingOpenAI()

        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            side_effect=create_client,
        ):
            pipeline = build_pipeline()

        response = pipeline.worker.execute(
            "Return valid JSON."
        )

        self.assertIn(
            "openai fallback",
            response,
        )

        self.assertEqual(
            pipeline.worker
            .last_attempts[-1]
            .provider,
            "openai",
        )

        self.assertTrue(
            pipeline.worker
            .last_attempts[-1]
            .successful
        )


if __name__ == "__main__":
    unittest.main()
