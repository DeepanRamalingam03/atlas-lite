from __future__ import annotations

from pathlib import Path

import config

from clients.base_client import BaseClient
from clients.gemini_client import GeminiClient
from clients.openai_client import OpenAIClient
from core.usage.token_ledger import (
    TokenUsageLedger,
)


DEFAULT_USAGE_PATH = Path(
    ".atlas_data/ai_token_usage.json"
)


class ClientFactory:
    """Creates configured AI provider clients."""

    @staticmethod
    def create(
        provider: str,
        usage_ledger: TokenUsageLedger | None = None,
    ) -> BaseClient:
        selected_provider = (
            provider.strip().lower()
        )

        ledger = (
            usage_ledger
            or TokenUsageLedger(
                storage_path=(
                    DEFAULT_USAGE_PATH
                )
            )
        )

        if selected_provider == "gemini":
            if not config.GEMINI_API_KEY:
                raise RuntimeError(
                    "GEMINI_API_KEY is missing."
                )

            return GeminiClient(
                api_key=config.GEMINI_API_KEY,
                model_name=config.GEMINI_MODEL,
                timeout=config.CLIENT_TIMEOUT,
                usage_ledger=ledger,
            )

        if selected_provider == "openai":
            if not config.OPENAI_API_KEY:
                raise RuntimeError(
                    "OPENAI_API_KEY is missing."
                )

            return OpenAIClient(
                api_key=config.OPENAI_API_KEY,
                model_name=config.OPENAI_MODEL,
                usage_ledger=ledger,
            )

        raise ValueError(
            f"Unsupported provider: {provider}"
        )
