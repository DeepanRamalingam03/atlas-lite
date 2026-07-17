from __future__ import annotations

import shutil
import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from pathlib import Path

from core.usage.pricing_engine import (
    PricingEngine,
)
from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
)
from discord_gateway.usage_controls import (
    DiscordUsageControls,
)


class DiscordUsageCostTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_usage_cost_test"
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
            15,
            0,
            0,
            tzinfo=timezone.utc,
        )

        self.controls = DiscordUsageControls(
            ledger=self.ledger,
            pricing_engine=PricingEngine(
                usd_inr_rate=Decimal("100")
            ),
            now_provider=lambda: self.now,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_usage_report_includes_cost(
        self,
    ) -> None:
        self._append(
            provider="openai",
            model="gpt-5.1",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
        )

        result = self.controls.usage(
            "today",
            "openai",
        )

        self.assertTrue(result.success)

        self.assertIn(
            "Estimated USD: `$11.250000`",
            result.message,
        )

        self.assertIn(
            "Estimated INR: `₹1125.0000`",
            result.message,
        )

        self.assertIn(
            "Estimated total INR: `₹1125.0000`",
            result.message,
        )

        self.assertIn(
            "1 USD = ₹100.0000",
            result.message,
        )

    def test_cached_cost_is_used(
        self,
    ) -> None:
        self._append(
            provider="openai",
            model="gpt-5.1",
            input_tokens=1_000_000,
            cached_input_tokens=400_000,
            total_tokens=1_000_000,
        )

        result = self.controls.usage(
            "today",
            "openai",
        )

        self.assertIn(
            "Estimated USD: `$0.800000`",
            result.message,
        )

        self.assertIn(
            "Estimated INR: `₹80.0000`",
            result.message,
        )

    def test_mixed_provider_total(
        self,
    ) -> None:
        self._append(
            provider="openai",
            model="gpt-5.1",
            input_tokens=1_000_000,
            total_tokens=1_000_000,
        )

        self._append(
            provider="gemini",
            model="gemini-3.5-flash",
            output_tokens=1_000_000,
            total_tokens=1_000_000,
        )

        result = self.controls.usage(
            "all",
            "all",
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
            "Estimated total USD: `$10.250000`",
            result.message,
        )

        self.assertIn(
            "Estimated total INR: `₹1025.0000`",
            result.message,
        )

    def test_unknown_model_is_unpriced(
        self,
    ) -> None:
        self._append(
            provider="openai",
            model="unknown-model",
            input_tokens=1000,
            output_tokens=1000,
            total_tokens=2000,
        )

        result = self.controls.usage(
            "today",
            "openai",
        )

        self.assertIn(
            "Priced requests: `0`",
            result.message,
        )

        self.assertIn(
            "Unpriced requests: `1`",
            result.message,
        )

        self.assertIn(
            "Estimated total USD: `$0.000000`",
            result.message,
        )

    def test_month_filter(
        self,
    ) -> None:
        self._append(
            provider="openai",
            model="gpt-5.1",
            total_tokens=100,
            timestamp=self.now,
        )

        self._append(
            provider="openai",
            model="gpt-5.1",
            total_tokens=900,
            timestamp=(
                self.now
                - timedelta(days=40)
            ),
        )

        result = self.controls.usage(
            "month",
            "openai",
        )

        self.assertIn(
            "Current month (UTC)",
            result.message,
        )

        self.assertIn(
            "Requests: `1`",
            result.message,
        )

    def test_empty_report_has_zero_cost(
        self,
    ) -> None:
        result = self.controls.usage()

        self.assertIn(
            "Estimated total USD: `$0.000000`",
            result.message,
        )

        self.assertIn(
            "Estimated total INR: `₹0.0000`",
            result.message,
        )

    def test_help_includes_month_and_cost(
        self,
    ) -> None:
        result = self.controls.help_message()

        self.assertIn(
            "!usage month",
            result.message,
        )

        self.assertIn(
            "Costs are estimates",
            result.message,
        )

    def _append(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cached_input_tokens: int = 0,
        timestamp: datetime | None = None,
    ) -> None:
        record = TokenUsageRecord(
            record_id=(
                f"record-"
                f"{len(self.ledger.list_all())}"
            ),
            timestamp=(
                timestamp or self.now
            ).isoformat(),
            provider=provider,
            model=model,
            success=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=(
                cached_input_tokens
            ),
        )

        self.ledger.append(record)


if __name__ == "__main__":
    unittest.main()
