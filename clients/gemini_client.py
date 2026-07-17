from __future__ import annotations

import time
from typing import Any

from google import genai
from google.genai import types

from clients.base_client import BaseClient
from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
)


class GeminiClient(BaseClient):
    """
    Gemini API client used by Atlas Lite workers.

    The public generate() contract remains plain text. Official response
    usage metadata is persisted separately when a ledger is configured.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        timeout: int = 60,
        usage_ledger: TokenUsageLedger | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError(
                "Gemini API key cannot be empty."
            )

        if not model_name.strip():
            raise ValueError(
                "Gemini model name cannot be empty."
            )

        if timeout <= 0:
            raise ValueError(
                "Timeout must be greater than zero."
            )

        self.model_name = model_name.strip()
        self.timeout_seconds = timeout
        self.usage_ledger = usage_ledger

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout * 1000
            ),
        )

    def generate(
        self,
        prompt: str,
    ) -> str:
        cleaned_prompt = prompt.strip()

        if not cleaned_prompt:
            raise ValueError(
                "Prompt cannot be empty."
            )

        started_at = time.perf_counter()

        try:
            response = (
                self.client.models
                .generate_content(
                    model=self.model_name,
                    contents=cleaned_prompt,
                )
            )
        except Exception as exc:
            self._record_failure(
                started_at=started_at,
                error=exc,
            )
            raise

        response_text = getattr(
            response,
            "text",
            None,
        )

        if not response_text:
            error = RuntimeError(
                "Gemini returned an empty response."
            )

            self._record_response(
                response=response,
                started_at=started_at,
                success=False,
                error_type=type(error).__name__,
            )

            raise error

        self._record_response(
            response=response,
            started_at=started_at,
            success=True,
            error_type=None,
        )

        return str(response_text).strip()

    def _record_response(
        self,
        *,
        response: Any,
        started_at: float,
        success: bool,
        error_type: str | None,
    ) -> None:
        if self.usage_ledger is None:
            return

        usage = getattr(
            response,
            "usage_metadata",
            None,
        )

        input_tokens = self._integer(
            getattr(
                usage,
                "prompt_token_count",
                0,
            )
        )

        output_tokens = self._integer(
            getattr(
                usage,
                "candidates_token_count",
                0,
            )
        )

        total_tokens = self._integer(
            getattr(
                usage,
                "total_token_count",
                0,
            )
        )

        cached_tokens = self._integer(
            getattr(
                usage,
                "cached_content_token_count",
                0,
            )
        )

        reasoning_tokens = self._integer(
            getattr(
                usage,
                "thoughts_token_count",
                0,
            )
        )

        tool_tokens = self._integer(
            getattr(
                usage,
                "tool_use_prompt_token_count",
                0,
            )
        )

        self.usage_ledger.append(
            TokenUsageRecord.create(
                provider="gemini",
                model=self.model_name,
                success=success,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cached_input_tokens=(
                    cached_tokens
                ),
                reasoning_tokens=(
                    reasoning_tokens
                ),
                tool_tokens=tool_tokens,
                latency_ms=self._elapsed_ms(
                    started_at
                ),
                error_type=error_type,
            )
        )

    def _record_failure(
        self,
        *,
        started_at: float,
        error: Exception,
    ) -> None:
        if self.usage_ledger is None:
            return

        self.usage_ledger.append(
            TokenUsageRecord.create(
                provider="gemini",
                model=self.model_name,
                success=False,
                latency_ms=self._elapsed_ms(
                    started_at
                ),
                error_type=type(error).__name__,
            )
        )

    @staticmethod
    def _integer(
        value: object,
    ) -> int:
        try:
            return max(
                0,
                int(value or 0),
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0

    @staticmethod
    def _elapsed_ms(
        started_at: float,
    ) -> int:
        return max(
            0,
            round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000
            ),
        )
