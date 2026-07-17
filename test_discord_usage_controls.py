from __future__ import annotations

import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
)
from discord_gateway.usage_controls import (
    DiscordUsageControls,
)


class DiscordUsageControlsTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_usage_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.ledger = TokenUsageLedger(
            self.root / "usage.json"
        )

        self.now = datetime(
            2026,
            7,
            17,
            12,
            0,
            0,
            tzinfo=timezone.utc,
        )

        self.controls = (
            DiscordUsageControls(
                ledger=self.ledger,
                now_provider=(
                    lambda: self.now
                ),
            )
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_empty_today_report(
        self,
    ) -> None:
        result = self.controls.usage()

        self.assertTrue(
            result.success
        )

        self.assertIn(
            "Today (UTC)",
            result.message,
        )

        self.assertIn(
            "Requests: `0`",
            result.message,
        )

        self.assertIn(
            "Total tokens: `0`",
            result.message,
        )

    def test_today_includes_current_records(
        self,
    ) -> None:
        self._append(
            provider="openai",
            timestamp=(
                self.now
                - timedelta(hours=1)
            ),
            input_tokens=1000,
            output_tokens=250,
            total_tokens=1250,
            latency_ms=500,
        )

        self._append(
            provider="gemini",
            timestamp=(
                self.now
                - timedelta(hours=2)
            ),
            input_tokens=2000,
            output_tokens=500,
            total_tokens=2500,
            latency_ms=700,
        )

        result = self.controls.usage(
            "today"
        )

        self.assertIn(
            "**Openai**",
            result.message,
        )

        self.assertIn(
            "**Gemini**",
            result.message,
        )

        self.assertIn(
            "Input tokens: `1,000`",
            result.message,
        )

        self.assertIn(
            "Total tokens: `3,750`",
            result.message,
        )

        self.assertIn(
            "Average tokens/request: `1,875.0`",
            result.message,
        )

    def test_today_excludes_yesterday(
        self,
    ) -> None:
        self._append(
            provider="openai",
            timestamp=(
                self.now
                - timedelta(days=1)
            ),
            total_tokens=999,
        )

        self._append(
            provider="openai",
            timestamp=(
                self.now
                - timedelta(hours=1)
            ),
            total_tokens=100,
        )

        result = self.controls.usage(
            "today",
            "openai",
        )

        self.assertIn(
            "Total tokens: `100`",
            result.message,
        )

        self.assertNotIn(
            "`999`",
            result.message,
        )

    def test_week_is_rolling_seven_days(
        self,
    ) -> None:
        self._append(
            provider="gemini",
            timestamp=(
                self.now
                - timedelta(days=6)
            ),
            total_tokens=600,
        )

        self._append(
            provider="gemini",
            timestamp=(
                self.now
                - timedelta(days=8)
            ),
            total_tokens=800,
        )

        result = self.controls.usage(
            "week",
            "gemini",
        )

        self.assertIn(
            "Rolling 7 days",
            result.message,
        )

        self.assertIn(
            "Total tokens: `600`",
            result.message,
        )

        self.assertNotIn(
            "`800`",
            result.message,
        )

    def test_all_includes_all_records(
        self,
    ) -> None:
        self._append(
            provider="openai",
            timestamp=(
                self.now
                - timedelta(days=30)
            ),
            total_tokens=100,
        )

        self._append(
            provider="gemini",
            timestamp=self.now,
            total_tokens=200,
        )

        result = self.controls.usage(
            "all"
        )

        self.assertIn(
            "All retained history",
            result.message,
        )

        self.assertIn(
            "Total tokens: `300`",
            result.message,
        )

    def test_provider_filter(
        self,
    ) -> None:
        self._append(
            provider="openai",
            timestamp=self.now,
            total_tokens=100,
        )

        self._append(
            provider="gemini",
            timestamp=self.now,
            total_tokens=200,
        )

        result = self.controls.usage(
            "all",
            "openai",
        )

        self.assertIn(
            "**Openai**",
            result.message,
        )

        self.assertNotIn(
            "**Gemini**",
            result.message,
        )

        self.assertIn(
            "Total tokens: `100`",
            result.message,
        )

    def test_failed_request_statistics(
        self,
    ) -> None:
        self._append(
            provider="gemini",
            timestamp=self.now,
            success=False,
            error_type="ServerError",
        )

        result = self.controls.usage(
            "today",
            "gemini",
        )

        self.assertIn(
            "Requests: `1`",
            result.message,
        )

        self.assertIn(
            "Successful: `0`",
            result.message,
        )

        self.assertIn(
            "Failed: `1`",
            result.message,
        )

        self.assertIn(
            "Success rate: `0.0%`",
            result.message,
        )

    def test_additional_token_types(
        self,
    ) -> None:
        self._append(
            provider="gemini",
            timestamp=self.now,
            total_tokens=100,
            cached_input_tokens=10,
            reasoning_tokens=20,
            tool_tokens=5,
        )

        result = self.controls.usage(
            "today",
            "gemini",
        )

        self.assertIn(
            "Cached input: `10`",
            result.message,
        )

        self.assertIn(
            "Reasoning/thoughts: `20`",
            result.message,
        )

        self.assertIn(
            "Tool tokens: `5`",
            result.message,
        )

    def test_invalid_period(
        self,
    ) -> None:
        result = self.controls.usage(
            "year"
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Invalid usage period",
            result.message,
        )

    def test_invalid_provider(
        self,
    ) -> None:
        result = self.controls.usage(
            "today",
            "unknown",
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Invalid provider",
            result.message,
        )

    def test_help_message(
        self,
    ) -> None:
        result = (
            self.controls
            .help_message()
        )

        self.assertTrue(
            result.success
        )

        self.assertIn(
            "!usage week",
            result.message,
        )

        self.assertIn(
            "!usage all gemini",
            result.message,
        )

        self.assertIn(
            "Prompts and responses are not stored",
            result.message,
        )

    def test_naive_now_is_treated_as_utc(
        self,
    ) -> None:
        controls = (
            DiscordUsageControls(
                ledger=self.ledger,
                now_provider=(
                    lambda: datetime(
                        2026,
                        7,
                        17,
                        12,
                        0,
                        0,
                    )
                ),
            )
        )

        result = controls.usage()

        self.assertTrue(
            result.success
        )

        self.assertIn(
            "+00:00",
            result.message,
        )

    def _append(
        self,
        *,
        provider: str,
        timestamp: datetime,
        success: bool = True,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        tool_tokens: int = 0,
        latency_ms: int = 0,
        error_type: str | None = None,
    ) -> None:
        record = TokenUsageRecord(
            record_id=(
                f"record-{provider}-"
                f"{len(self.ledger.list_all())}"
            ),
            timestamp=(
                timestamp.isoformat()
            ),
            provider=provider,
            model=f"{provider}-model",
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=(
                cached_input_tokens
            ),
            reasoning_tokens=(
                reasoning_tokens
            ),
            tool_tokens=tool_tokens,
            latency_ms=latency_ms,
            error_type=error_type,
        )

        self.ledger.append(record)


if __name__ == "__main__":
    unittest.main()
