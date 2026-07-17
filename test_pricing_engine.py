from __future__ import annotations

import os
import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from unittest.mock import patch

from core.usage.pricing_catalog import (
    ModelPricing,
    PricingCatalog,
)
from core.usage.pricing_engine import (
    PricingEngine,
)
from core.usage.token_ledger import (
    TokenUsageRecord,
)


class PricingCatalogTest(unittest.TestCase):
    def test_gpt_5_1_official_rates(
        self,
    ) -> None:
        pricing = PricingCatalog().require(
            "openai",
            "gpt-5.1",
        )

        self.assertEqual(
            pricing.input_usd_per_million,
            Decimal("1.25"),
        )

        self.assertEqual(
            pricing.cached_input_usd_per_million,
            Decimal("0.125"),
        )

        self.assertEqual(
            pricing.output_usd_per_million,
            Decimal("10.00"),
        )

    def test_gemini_3_5_flash_official_rates(
        self,
    ) -> None:
        pricing = PricingCatalog().require(
            "gemini",
            "gemini-3.5-flash",
        )

        self.assertEqual(
            pricing.input_usd_per_million,
            Decimal("1.50"),
        )

        self.assertEqual(
            pricing.cached_input_usd_per_million,
            Decimal("0.15"),
        )

        self.assertEqual(
            pricing.output_usd_per_million,
            Decimal("9.00"),
        )

    def test_snapshot_model_resolves_to_base(
        self,
    ) -> None:
        pricing = PricingCatalog().find(
            "openai",
            "gpt-5.1-2025-11-13",
        )

        self.assertIsNotNone(pricing)

        self.assertEqual(
            pricing.model,
            "gpt-5.1",
        )

    def test_unknown_model_is_not_guessed(
        self,
    ) -> None:
        self.assertIsNone(
            PricingCatalog().find(
                "openai",
                "unknown-model",
            )
        )

    def test_environment_override(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "ATLAS_GPT_5_1_INPUT_USD_PER_1M": (
                    "2.50"
                )
            },
        ):
            pricing = PricingCatalog().require(
                "openai",
                "gpt-5.1",
            )

        self.assertEqual(
            pricing.input_usd_per_million,
            Decimal("2.50"),
        )


class PricingEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PricingEngine(
            usd_inr_rate=Decimal("100"),
        )

    def test_openai_cost_calculation(
        self,
    ) -> None:
        result = self.engine.calculate(
            self._record(
                provider="openai",
                model="gpt-5.1",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                total_tokens=2_000_000,
            )
        )

        self.assertTrue(result.priced)

        self.assertEqual(
            result.input_cost_usd,
            Decimal("1.250000"),
        )

        self.assertEqual(
            result.output_cost_usd,
            Decimal("10.000000"),
        )

        self.assertEqual(
            result.total_cost_usd,
            Decimal("11.250000"),
        )

        self.assertEqual(
            result.total_cost_inr,
            Decimal("1125.0000"),
        )

    def test_gemini_cost_calculation(
        self,
    ) -> None:
        result = self.engine.calculate(
            self._record(
                provider="gemini",
                model="gemini-3.5-flash",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                total_tokens=2_000_000,
            )
        )

        self.assertEqual(
            result.total_cost_usd,
            Decimal("10.500000"),
        )

        self.assertEqual(
            result.total_cost_inr,
            Decimal("1050.0000"),
        )

    def test_cached_tokens_are_not_double_charged(
        self,
    ) -> None:
        result = self.engine.calculate(
            self._record(
                provider="openai",
                model="gpt-5.1",
                input_tokens=1_000_000,
                cached_input_tokens=400_000,
                output_tokens=0,
                total_tokens=1_000_000,
            )
        )

        self.assertEqual(
            result.input_cost_usd,
            Decimal("0.750000"),
        )

        self.assertEqual(
            result.cached_input_cost_usd,
            Decimal("0.050000"),
        )

        self.assertEqual(
            result.total_cost_usd,
            Decimal("0.800000"),
        )

    def test_failed_zero_token_call_has_zero_cost(
        self,
    ) -> None:
        result = self.engine.calculate(
            self._record(
                provider="gemini",
                model="gemini-3.5-flash",
                success=False,
            )
        )

        self.assertTrue(result.priced)

        self.assertEqual(
            result.total_cost_usd,
            Decimal("0.000000"),
        )

        self.assertEqual(
            result.total_cost_inr,
            Decimal("0.0000"),
        )

    def test_unknown_model_is_unpriced(
        self,
    ) -> None:
        result = self.engine.calculate(
            self._record(
                provider="openai",
                model="future-model",
                input_tokens=100,
                output_tokens=100,
                total_tokens=200,
            )
        )

        self.assertFalse(result.priced)

        self.assertEqual(
            result.total_cost_usd,
            Decimal("0"),
        )

        self.assertIn(
            "No pricing configured",
            result.unpriced_reason or "",
        )

    def test_summary_mixed_providers(
        self,
    ) -> None:
        records = [
            self._record(
                provider="openai",
                model="gpt-5.1",
                input_tokens=1_000_000,
                total_tokens=1_000_000,
            ),
            self._record(
                provider="gemini",
                model="gemini-3.5-flash",
                output_tokens=1_000_000,
                total_tokens=1_000_000,
            ),
        ]

        summary = self.engine.summarize(
            records
        )

        self.assertEqual(
            summary.request_count,
            2,
        )

        self.assertEqual(
            summary.priced_requests,
            2,
        )

        self.assertEqual(
            summary.total_cost_usd,
            Decimal("10.250000"),
        )

        self.assertEqual(
            summary.total_cost_inr,
            Decimal("1025.000000"),
        )

    def test_provider_filter(
        self,
    ) -> None:
        records = [
            self._record(
                provider="openai",
                model="gpt-5.1",
                input_tokens=1_000_000,
                total_tokens=1_000_000,
            ),
            self._record(
                provider="gemini",
                model="gemini-3.5-flash",
                input_tokens=1_000_000,
                total_tokens=1_000_000,
            ),
        ]

        summary = self.engine.summarize(
            records,
            provider="openai",
        )

        self.assertEqual(
            summary.request_count,
            1,
        )

        self.assertEqual(
            summary.total_cost_usd,
            Decimal("1.250000"),
        )

    def test_since_filter(
        self,
    ) -> None:
        old_record = TokenUsageRecord(
            record_id="old",
            timestamp=(
                datetime.now(timezone.utc)
                - timedelta(days=2)
            ).isoformat(),
            provider="openai",
            model="gpt-5.1",
            success=True,
            input_tokens=1_000_000,
            output_tokens=0,
            total_tokens=1_000_000,
        )

        current_record = self._record(
            provider="openai",
            model="gpt-5.1",
            output_tokens=1_000_000,
            total_tokens=1_000_000,
        )

        summary = self.engine.summarize(
            [
                old_record,
                current_record,
            ],
            since=(
                datetime.now(timezone.utc)
                - timedelta(hours=1)
            ),
        )

        self.assertEqual(
            summary.request_count,
            1,
        )

        self.assertEqual(
            summary.total_cost_usd,
            Decimal("10.000000"),
        )

    def test_custom_catalog(
        self,
    ) -> None:
        catalog = PricingCatalog(
            prices=(
                ModelPricing(
                    provider="custom",
                    model="custom-model",
                    input_usd_per_million=(
                        Decimal("2")
                    ),
                    cached_input_usd_per_million=(
                        Decimal("1")
                    ),
                    output_usd_per_million=(
                        Decimal("4")
                    ),
                ),
            )
        )

        engine = PricingEngine(
            catalog=catalog,
            usd_inr_rate="80",
        )

        result = engine.calculate(
            self._record(
                provider="custom",
                model="custom-model",
                input_tokens=500_000,
                output_tokens=500_000,
                total_tokens=1_000_000,
            )
        )

        self.assertEqual(
            result.total_cost_usd,
            Decimal("3.000000"),
        )

        self.assertEqual(
            result.total_cost_inr,
            Decimal("240.0000"),
        )

    def test_invalid_exchange_rate_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            PricingEngine(
                usd_inr_rate="0"
            )

    @staticmethod
    def _record(
        *,
        provider: str,
        model: str,
        success: bool = True,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cached_input_tokens: int = 0,
    ) -> TokenUsageRecord:
        return TokenUsageRecord.create(
            provider=provider,
            model=model,
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=(
                cached_input_tokens
            ),
        )


if __name__ == "__main__":
    unittest.main()
