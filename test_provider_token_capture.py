from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace

from clients.gemini_client import (
    GeminiClient,
)
from clients.openai_client import (
    OpenAIClient,
)
from core.usage.token_ledger import (
    TokenUsageLedger,
)


class FakeOpenAIResponses:
    def __init__(
        self,
        response=None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    def create(
        self,
        **kwargs,
    ):
        if self.error is not None:
            raise self.error

        return self.response


class FakeGeminiModels:
    def __init__(
        self,
        response=None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    def generate_content(
        self,
        **kwargs,
    ):
        if self.error is not None:
            raise self.error

        return self.response


class ProviderTokenCaptureTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_provider_usage_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.ledger = TokenUsageLedger(
            self.root / "usage.json"
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_openai_usage_is_recorded(
        self,
    ) -> None:
        client = OpenAIClient(
            api_key="test-key",
            model_name="gpt-test",
            usage_ledger=self.ledger,
        )

        response = SimpleNamespace(
            output_text="manager response",
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
                input_tokens_details=(
                    SimpleNamespace(
                        cached_tokens=20
                    )
                ),
                output_tokens_details=(
                    SimpleNamespace(
                        reasoning_tokens=5
                    )
                ),
            ),
        )

        client.client = SimpleNamespace(
            responses=FakeOpenAIResponses(
                response=response
            )
        )

        result = client.generate(
            "Test prompt"
        )

        self.assertEqual(
            result,
            "manager response",
        )

        record = self.ledger.list_all()[0]

        self.assertEqual(
            record.provider,
            "openai",
        )

        self.assertEqual(
            record.input_tokens,
            100,
        )

        self.assertEqual(
            record.output_tokens,
            25,
        )

        self.assertEqual(
            record.total_tokens,
            125,
        )

        self.assertEqual(
            record.cached_input_tokens,
            20,
        )

        self.assertEqual(
            record.reasoning_tokens,
            5,
        )

        self.assertTrue(record.success)

    def test_gemini_usage_is_recorded(
        self,
    ) -> None:
        client = GeminiClient(
            api_key="test-key",
            model_name="gemini-test",
            timeout=30,
            usage_ledger=self.ledger,
        )

        response = SimpleNamespace(
            text="worker response",
            usage_metadata=SimpleNamespace(
                prompt_token_count=200,
                candidates_token_count=40,
                total_token_count=260,
                cached_content_token_count=15,
                thoughts_token_count=10,
                tool_use_prompt_token_count=10,
            ),
        )

        client.client = SimpleNamespace(
            models=FakeGeminiModels(
                response=response
            )
        )

        result = client.generate(
            "Test prompt"
        )

        self.assertEqual(
            result,
            "worker response",
        )

        record = self.ledger.list_all()[0]

        self.assertEqual(
            record.provider,
            "gemini",
        )

        self.assertEqual(
            record.input_tokens,
            200,
        )

        self.assertEqual(
            record.output_tokens,
            40,
        )

        self.assertEqual(
            record.total_tokens,
            260,
        )

        self.assertEqual(
            record.cached_input_tokens,
            15,
        )

        self.assertEqual(
            record.reasoning_tokens,
            10,
        )

        self.assertEqual(
            record.tool_tokens,
            10,
        )

        self.assertTrue(record.success)

    def test_openai_failure_is_recorded(
        self,
    ) -> None:
        client = OpenAIClient(
            api_key="test-key",
            model_name="gpt-test",
            usage_ledger=self.ledger,
        )

        client.client = SimpleNamespace(
            responses=FakeOpenAIResponses(
                error=RuntimeError(
                    "provider unavailable"
                )
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            client.generate(
                "Test prompt"
            )

        record = self.ledger.list_all()[0]

        self.assertFalse(record.success)

        self.assertEqual(
            record.error_type,
            "RuntimeError",
        )

        self.assertEqual(
            record.total_tokens,
            0,
        )

    def test_gemini_failure_is_recorded(
        self,
    ) -> None:
        client = GeminiClient(
            api_key="test-key",
            model_name="gemini-test",
            usage_ledger=self.ledger,
        )

        client.client = SimpleNamespace(
            models=FakeGeminiModels(
                error=RuntimeError(
                    "provider unavailable"
                )
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            client.generate(
                "Test prompt"
            )

        record = self.ledger.list_all()[0]

        self.assertFalse(record.success)

        self.assertEqual(
            record.error_type,
            "RuntimeError",
        )

    def test_client_without_ledger_remains_compatible(
        self,
    ) -> None:
        client = OpenAIClient(
            api_key="test-key",
            model_name="gpt-test",
        )

        client.client = SimpleNamespace(
            responses=FakeOpenAIResponses(
                response=SimpleNamespace(
                    output_text="ok",
                    usage=None,
                )
            )
        )

        self.assertEqual(
            client.generate("prompt"),
            "ok",
        )


if __name__ == "__main__":
    unittest.main()
