from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)
from typing import Iterable

from core.usage.pricing_catalog import (
    ModelPricing,
    ONE_MILLION,
    PricingCatalog,
)
from core.usage.token_ledger import (
    TokenUsageRecord,
)


USD_QUANTUM = Decimal("0.000001")
INR_QUANTUM = Decimal("0.0001")


@dataclass(slots=True, frozen=True)
class UsageCost:
    record_id: str
    provider: str
    model: str
    priced: bool
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    input_cost_usd: Decimal
    cached_input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal
    total_cost_inr: Decimal
    usd_inr_rate: Decimal
    pricing_note: str = ""
    unpriced_reason: str | None = None


@dataclass(slots=True, frozen=True)
class CostSummary:
    request_count: int
    priced_requests: int
    unpriced_requests: int
    successful_requests: int
    failed_requests: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: Decimal
    cached_input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal
    total_cost_inr: Decimal
    usd_inr_rate: Decimal

    @property
    def average_cost_usd_per_request(
        self,
    ) -> Decimal:
        if self.request_count == 0:
            return Decimal("0")

        return (
            self.total_cost_usd
            / Decimal(self.request_count)
        ).quantize(
            USD_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    @property
    def average_cost_inr_per_request(
        self,
    ) -> Decimal:
        if self.request_count == 0:
            return Decimal("0")

        return (
            self.total_cost_inr
            / Decimal(self.request_count)
        ).quantize(
            INR_QUANTUM,
            rounding=ROUND_HALF_UP,
        )


class PricingEngine:
    """
    Converts official provider token usage into estimated USD and INR cost.

    Prompts and model responses are never required or stored.

    Cached tokens are removed from normal input tokens before charging:
        normal_input = input_tokens - cached_input_tokens

    Reasoning/thinking tokens are not charged separately because provider
    usage metadata includes them in output-token billing for these models.
    """

    def __init__(
        self,
        catalog: PricingCatalog | None = None,
        *,
        usd_inr_rate: Decimal | str | float | None = None,
    ) -> None:
        self.catalog = (
            catalog or PricingCatalog()
        )

        self.usd_inr_rate = (
            self._resolve_usd_inr_rate(
                usd_inr_rate
            )
        )

    def calculate(
        self,
        record: TokenUsageRecord,
    ) -> UsageCost:
        pricing = self.catalog.find(
            record.provider,
            record.model,
        )

        if pricing is None:
            return UsageCost(
                record_id=record.record_id,
                provider=record.provider,
                model=record.model,
                priced=False,
                input_tokens=record.input_tokens,
                cached_input_tokens=(
                    record.cached_input_tokens
                ),
                output_tokens=record.output_tokens,
                input_cost_usd=Decimal("0"),
                cached_input_cost_usd=(
                    Decimal("0")
                ),
                output_cost_usd=Decimal("0"),
                total_cost_usd=Decimal("0"),
                total_cost_inr=Decimal("0"),
                usd_inr_rate=self.usd_inr_rate,
                unpriced_reason=(
                    "No pricing configured for "
                    f"{record.provider}/{record.model}."
                ),
            )

        return self._calculate_priced(
            record=record,
            pricing=pricing,
        )

    def summarize(
        self,
        records: Iterable[
            TokenUsageRecord
        ],
        *,
        provider: str | None = None,
        model: str | None = None,
        since: datetime | None = None,
    ) -> CostSummary:
        selected_provider = (
            provider.strip().lower()
            if provider
            else None
        )

        selected_model = (
            model.strip().lower()
            if model
            else None
        )

        selected_records: list[
            TokenUsageRecord
        ] = []

        for record in records:
            if (
                selected_provider is not None
                and record.provider.lower()
                != selected_provider
            ):
                continue

            if (
                selected_model is not None
                and record.model.lower()
                != selected_model
            ):
                continue

            if (
                since is not None
                and not self._is_since(
                    record,
                    since,
                )
            ):
                continue

            selected_records.append(record)

        calculated = [
            self.calculate(record)
            for record in selected_records
        ]

        return CostSummary(
            request_count=len(selected_records),
            priced_requests=sum(
                item.priced
                for item in calculated
            ),
            unpriced_requests=sum(
                not item.priced
                for item in calculated
            ),
            successful_requests=sum(
                record.success
                for record in selected_records
            ),
            failed_requests=sum(
                not record.success
                for record in selected_records
            ),
            input_tokens=sum(
                record.input_tokens
                for record in selected_records
            ),
            cached_input_tokens=sum(
                record.cached_input_tokens
                for record in selected_records
            ),
            output_tokens=sum(
                record.output_tokens
                for record in selected_records
            ),
            total_tokens=sum(
                record.total_tokens
                for record in selected_records
            ),
            input_cost_usd=self._sum_decimal(
                item.input_cost_usd
                for item in calculated
            ),
            cached_input_cost_usd=(
                self._sum_decimal(
                    item.cached_input_cost_usd
                    for item in calculated
                )
            ),
            output_cost_usd=self._sum_decimal(
                item.output_cost_usd
                for item in calculated
            ),
            total_cost_usd=self._sum_decimal(
                item.total_cost_usd
                for item in calculated
            ),
            total_cost_inr=self._sum_decimal(
                item.total_cost_inr
                for item in calculated
            ),
            usd_inr_rate=self.usd_inr_rate,
        )

    def summarize_by_provider(
        self,
        records: Iterable[
            TokenUsageRecord
        ],
        *,
        since: datetime | None = None,
    ) -> dict[str, CostSummary]:
        materialized = list(records)

        providers = sorted(
            {
                record.provider.lower()
                for record in materialized
            }
        )

        return {
            provider: self.summarize(
                materialized,
                provider=provider,
                since=since,
            )
            for provider in providers
        }

    def _calculate_priced(
        self,
        *,
        record: TokenUsageRecord,
        pricing: ModelPricing,
    ) -> UsageCost:
        cached_tokens = min(
            record.cached_input_tokens,
            record.input_tokens,
        )

        normal_input_tokens = max(
            0,
            record.input_tokens
            - cached_tokens,
        )

        input_cost = self._token_cost(
            normal_input_tokens,
            pricing.input_usd_per_million,
        )

        cached_cost = self._token_cost(
            cached_tokens,
            pricing.cached_input_usd_per_million,
        )

        output_cost = self._token_cost(
            record.output_tokens,
            pricing.output_usd_per_million,
        )

        total_usd = (
            input_cost
            + cached_cost
            + output_cost
        ).quantize(
            USD_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        total_inr = (
            total_usd
            * self.usd_inr_rate
        ).quantize(
            INR_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        return UsageCost(
            record_id=record.record_id,
            provider=record.provider,
            model=record.model,
            priced=True,
            input_tokens=record.input_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=record.output_tokens,
            input_cost_usd=input_cost,
            cached_input_cost_usd=(
                cached_cost
            ),
            output_cost_usd=output_cost,
            total_cost_usd=total_usd,
            total_cost_inr=total_inr,
            usd_inr_rate=self.usd_inr_rate,
            pricing_note=pricing.source_note,
        )

    @staticmethod
    def _token_cost(
        tokens: int,
        rate_per_million: Decimal,
    ) -> Decimal:
        return (
            Decimal(max(0, tokens))
            * rate_per_million
            / ONE_MILLION
        ).quantize(
            USD_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _sum_decimal(
        values: Iterable[Decimal],
    ) -> Decimal:
        return sum(
            values,
            Decimal("0"),
        ).quantize(
            USD_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _is_since(
        record: TokenUsageRecord,
        since: datetime,
    ) -> bool:
        normalized_since = since

        if normalized_since.tzinfo is None:
            normalized_since = (
                normalized_since.replace(
                    tzinfo=datetime.now()
                    .astimezone()
                    .tzinfo
                )
            )

        try:
            record_time = datetime.fromisoformat(
                record.timestamp
            )
        except ValueError:
            return False

        return record_time >= normalized_since

    @staticmethod
    def _resolve_usd_inr_rate(
        value: Decimal | str | float | None,
    ) -> Decimal:
        raw_value: object = value

        if raw_value is None:
            raw_value = os.getenv(
                "ATLAS_USD_INR_RATE",
                "96.32",
            )

        try:
            resolved = Decimal(
                str(raw_value).strip()
            )
        except (
            InvalidOperation,
            ValueError,
        ) as exc:
            raise ValueError(
                "USD/INR rate must be a valid decimal."
            ) from exc

        if resolved <= Decimal("0"):
            raise ValueError(
                "USD/INR rate must be greater than zero."
            )

        return resolved.quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )


__all__ = [
    "CostSummary",
    "PricingEngine",
    "UsageCost",
]
