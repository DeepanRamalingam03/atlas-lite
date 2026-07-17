from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from clients.base_client import BaseClient
from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
)


class OpenAIClient(BaseClient):
    """
    OpenAI provider used by the Atlas Lite Manager.

    The public generate() contract remains plain text. Official response
    usage metadata is persisted separately when a ledger is configured.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        usage_ledger: TokenUsageLedger | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError(
                "OpenAI API key cannot be empty."
            )

        if not model_name.strip():
            raise ValueError(
                "OpenAI model name cannot be empty."
            )

        self.model_name = model_name.strip()
        self.client = OpenAI(
            api_key=api_key
        )
        self.usage_ledger = usage_ledger

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
                self.client.responses.create(
                    model=self.model_name,
                    input=cleaned_prompt,
                )
            )
        except Exception as exc:
            self._record_failure(
                started_at=started_at,
                error=exc,
            )
            raise

        output_text = str(
            getattr(
                response,
                "output_text",
                "",
            )
            or ""
        ).strip()

        if not output_text:
            error = RuntimeError(
                "OpenAI returned an empty response."
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

        return output_text

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
            "usage",
            None,
        )

        input_tokens = self._integer(
            getattr(
                usage,
                "input_tokens",
                0,
            )
        )

        output_tokens = self._integer(
            getattr(
                usage,
                "output_tokens",
                0,
            )
        )

        total_tokens = self._integer(
            getattr(
                usage,
                "total_tokens",
                0,
            )
        )

        input_details = getattr(
            usage,
            "input_tokens_details",
            None,
        )

        output_details = getattr(
            usage,
            "output_tokens_details",
            None,
        )

        cached_tokens = self._integer(
            getattr(
                input_details,
                "cached_tokens",
                0,
            )
        )

        reasoning_tokens = self._integer(
            getattr(
                output_details,
                "reasoning_tokens",
                0,
            )
        )

        self.usage_ledger.append(
            TokenUsageRecord.create(
                provider="openai",
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
                provider="openai",
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
