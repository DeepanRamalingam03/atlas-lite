from __future__ import annotations

import config

from clients.base_client import BaseClient
from clients.gemini_client import GeminiClient
from clients.openai_client import OpenAIClient


class ClientFactory:
    """Creates configured AI provider clients."""

    @staticmethod
    def create(provider: str) -> BaseClient:
        selected_provider = provider.strip().lower()

        if selected_provider == "gemini":
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is missing.")

            return GeminiClient(
                api_key=config.GEMINI_API_KEY,
                model_name=config.GEMINI_MODEL,
                timeout=config.CLIENT_TIMEOUT,
            )

        if selected_provider == "openai":
            if not config.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is missing.")

            return OpenAIClient(
                api_key=config.OPENAI_API_KEY,
                model_name=config.OPENAI_MODEL,
            )

        raise ValueError(f"Unsupported provider: {provider}")
