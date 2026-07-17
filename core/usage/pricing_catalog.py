from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


ONE_MILLION = Decimal("1000000")


@dataclass(slots=True, frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    pricing_mode: str = "standard"
    source_note: str = ""

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError(
                "Pricing provider cannot be empty."
            )

        if not self.model.strip():
            raise ValueError(
                "Pricing model cannot be empty."
            )

        for field_name, value in {
            "input_usd_per_million": (
                self.input_usd_per_million
            ),
            "cached_input_usd_per_million": (
                self.cached_input_usd_per_million
            ),
            "output_usd_per_million": (
                self.output_usd_per_million
            ),
        }.items():
            if value < Decimal("0"):
                raise ValueError(
                    f"{field_name} cannot be negative."
                )


class PricingCatalog:
    """
    Version-controlled model pricing registry.

    Defaults represent standard paid API pricing. Environment overrides
    allow rates to be updated without changing source code.

    Unknown models are deliberately not estimated using another model's
    price. They remain unpriced until explicitly configured.
    """

    def __init__(
        self,
        prices: tuple[ModelPricing, ...] | None = None,
    ) -> None:
        configured_prices = (
            prices
            if prices is not None
            else self._default_prices()
        )

        self._prices = {
            (
                price.provider.strip().lower(),
                price.model.strip().lower(),
            ): price
            for price in configured_prices
        }

    def find(
        self,
        provider: str,
        model: str,
    ) -> ModelPricing | None:
        key = (
            provider.strip().lower(),
            model.strip().lower(),
        )

        exact = self._prices.get(key)

        if exact is not None:
            return exact

        normalized_model = self._normalize_snapshot(
            model
        )

        return self._prices.get(
            (
                provider.strip().lower(),
                normalized_model,
            )
        )

    def require(
        self,
        provider: str,
        model: str,
    ) -> ModelPricing:
        pricing = self.find(
            provider,
            model,
        )

        if pricing is None:
            raise KeyError(
                "No pricing configured for "
                f"{provider}/{model}."
            )

        return pricing

    def list_all(
        self,
    ) -> tuple[ModelPricing, ...]:
        return tuple(
            sorted(
                self._prices.values(),
                key=lambda item: (
                    item.provider,
                    item.model,
                ),
            )
        )

    @classmethod
    def _default_prices(
        cls,
    ) -> tuple[ModelPricing, ...]:
        return (
            ModelPricing(
                provider="openai",
                model="gpt-5.1",
                input_usd_per_million=(
                    cls._environment_decimal(
                        "ATLAS_GPT_5_1_INPUT_USD_PER_1M",
                        "1.25",
                    )
                ),
                cached_input_usd_per_million=(
                    cls._environment_decimal(
                        "ATLAS_GPT_5_1_CACHED_USD_PER_1M",
                        "0.125",
                    )
                ),
                output_usd_per_million=(
                    cls._environment_decimal(
                        "ATLAS_GPT_5_1_OUTPUT_USD_PER_1M",
                        "10.00",
                    )
                ),
                source_note=(
                    "OpenAI standard API text-token pricing."
                ),
            ),
            ModelPricing(
                provider="gemini",
                model="gemini-3.5-flash",
                input_usd_per_million=(
                    cls._environment_decimal(
                        "ATLAS_GEMINI_3_5_FLASH_INPUT_USD_PER_1M",
                        "1.50",
                    )
                ),
                cached_input_usd_per_million=(
                    cls._environment_decimal(
                        "ATLAS_GEMINI_3_5_FLASH_CACHED_USD_PER_1M",
                        "0.15",
                    )
                ),
                output_usd_per_million=(
                    cls._environment_decimal(
                        "ATLAS_GEMINI_3_5_FLASH_OUTPUT_USD_PER_1M",
                        "9.00",
                    )
                ),
                source_note=(
                    "Google Gemini standard paid-tier pricing. "
                    "Output price includes thinking tokens."
                ),
            ),
        )

    @staticmethod
    def _normalize_snapshot(
        model: str,
    ) -> str:
        normalized = model.strip().lower()

        known_prefixes = (
            "gpt-5.1-",
            "gemini-3.5-flash-",
        )

        for prefix in known_prefixes:
            if normalized.startswith(prefix):
                return prefix.rstrip("-")

        return normalized

    @staticmethod
    def _environment_decimal(
        name: str,
        default: str,
    ) -> Decimal:
        raw_value = os.getenv(
            name,
            default,
        )

        try:
            value = Decimal(
                str(raw_value).strip()
            )
        except (
            InvalidOperation,
            ValueError,
        ) as exc:
            raise ValueError(
                f"{name} must be a valid decimal."
            ) from exc

        if value < Decimal("0"):
            raise ValueError(
                f"{name} cannot be negative."
            )

        return value


__all__ = [
    "ModelPricing",
    "ONE_MILLION",
    "PricingCatalog",
]
