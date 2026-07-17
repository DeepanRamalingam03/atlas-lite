from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import Callable

from core.usage.pricing_engine import (
    CostSummary,
    PricingEngine,
)
from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
    TokenUsageSummary,
)


@dataclass(slots=True, frozen=True)
class UsageControlResult:
    success: bool
    message: str


class DiscordUsageControls:
    """
    Read-only Discord reporting surface for Atlas AI usage and cost.

    Supported periods:
    - today: current UTC calendar day
    - week: rolling seven days
    - month: current UTC calendar month
    - all: all retained ledger history

    Supported providers:
    - all
    - openai
    - gemini

    Token values come from provider response metadata.
    Cost values are estimates based on the configured pricing catalog
    and configured USD/INR exchange rate.

    This component never clears or modifies usage records.
    """

    VALID_PERIODS = frozenset(
        {
            "today",
            "week",
            "month",
            "all",
        }
    )

    VALID_PROVIDERS = frozenset(
        {
            "all",
            "openai",
            "gemini",
        }
    )

    def __init__(
        self,
        ledger: TokenUsageLedger,
        *,
        pricing_engine: PricingEngine | None = None,
        now_provider: (
            Callable[[], datetime] | None
        ) = None,
    ) -> None:
        self.ledger = ledger
        self.pricing_engine = (
            pricing_engine
            or PricingEngine()
        )
        self.now_provider = (
            now_provider
            or (
                lambda: datetime.now(
                    timezone.utc
                )
            )
        )

    def usage(
        self,
        period: str = "today",
        provider: str = "all",
    ) -> UsageControlResult:
        selected_period = (
            period.strip().lower()
            or "today"
        )

        selected_provider = (
            provider.strip().lower()
            or "all"
        )

        validation_error = self._validate(
            period=selected_period,
            provider=selected_provider,
        )

        if validation_error is not None:
            return UsageControlResult(
                success=False,
                message=validation_error,
            )

        now = self._normalized_now()

        since = self._since(
            period=selected_period,
            now=now,
        )

        records = self._filter_records(
            records=self.ledger.list_all(),
            provider=selected_provider,
            since=since,
        )

        provider_summaries = (
            self._summaries_by_provider(
                records
            )
        )

        overall = (
            self._summarize_tokens(
                records
            )
        )

        provider_costs = (
            self.pricing_engine
            .summarize_by_provider(
                records
            )
        )

        overall_cost = (
            self.pricing_engine.summarize(
                records
            )
        )

        message = self._render(
            period=selected_period,
            provider=selected_provider,
            provider_summaries=(
                provider_summaries
            ),
            provider_costs=provider_costs,
            overall=overall,
            overall_cost=overall_cost,
            generated_at=now,
        )

        return UsageControlResult(
            success=True,
            message=message,
        )

    def cost(
        self,
        period: str = "today",
        provider: str = "all",
    ) -> UsageControlResult:
        selected_period = (
            period.strip().lower()
            or "today"
        )

        selected_provider = (
            provider.strip().lower()
            or "all"
        )

        validation_error = self._validate(
            period=selected_period,
            provider=selected_provider,
        )

        if validation_error is not None:
            return UsageControlResult(
                success=False,
                message=validation_error,
            )

        now = self._normalized_now()

        since = self._since(
            period=selected_period,
            now=now,
        )

        records = self._filter_records(
            records=self.ledger.list_all(),
            provider=selected_provider,
            since=since,
        )

        provider_costs = (
            self.pricing_engine
            .summarize_by_provider(
                records
            )
        )

        overall_cost = (
            self.pricing_engine.summarize(
                records
            )
        )

        message = self._render_cost_report(
            period=selected_period,
            provider=selected_provider,
            provider_costs=provider_costs,
            overall_cost=overall_cost,
            generated_at=now,
        )

        return UsageControlResult(
            success=True,
            message=message,
        )

    def help_message(
        self,
    ) -> UsageControlResult:
        return UsageControlResult(
            success=True,
            message=(
                "**Atlas AI Usage Commands**\n"
                "`!usage` - today's usage and cost\n"
                "`!usage today`\n"
                "`!usage week`\n"
                "`!usage month`\n"
                "`!usage all`\n"
                "`!usage today openai`\n"
                "`!usage today gemini`\n"
                "`!usage week openai`\n"
                "`!usage month gemini`\n"
                "`!usage all gemini`\n"
                "`!cost` - today's estimated cost\n"
                "`!cost today`\n"
                "`!cost week`\n"
                "`!cost month`\n"
                "`!cost all`\n"
                "`!cost all openai`\n"
                "`!cost all gemini`\n\n"
                "Token values come from official "
                "provider response metadata.\n"
                "Costs are estimates based on the "
                "configured model prices and USD/INR rate.\n"
                "Prompts and responses are not stored."
            ),
        )

    def _render_cost_report(
        self,
        *,
        period: str,
        provider: str,
        provider_costs: dict[
            str,
            CostSummary,
        ],
        overall_cost: CostSummary,
        generated_at: datetime,
    ) -> str:
        sections: list[str] = [
            "**Atlas AI Estimated Cost**",
            (
                "Period: "
                f"`{self._period_title(period)}`"
            ),
            (
                "Provider filter: "
                f"`{provider}`"
            ),
            (
                "Generated: "
                f"`{generated_at.isoformat()}`"
            ),
        ]

        ordered_providers = [
            name
            for name in (
                "openai",
                "gemini",
            )
            if name in provider_costs
        ]

        additional_providers = sorted(
            set(provider_costs)
            - set(ordered_providers)
        )

        for provider_name in (
            ordered_providers
            + additional_providers
        ):
            summary = provider_costs[
                provider_name
            ]

            sections.append(
                self._render_provider_cost(
                    provider=provider_name,
                    summary=summary,
                )
            )

        if not provider_costs:
            sections.append(
                "\nNo priced or unpriced AI calls "
                "were found for this period."
            )

        sections.append(
            self._render_total_cost(
                overall_cost
            )
        )

        sections.append(
            "\n**Estimation Basis**\n"
            "- Model prices come from the "
            "configured Atlas pricing catalog.\n"
            "- Exchange rate: "
            f"`1 USD = ₹{overall_cost.usd_inr_rate:.4f}`\n"
            "- This is an estimate and may differ "
            "from the provider invoice or card charge.\n"
            "- Calls using an unknown model are "
            "shown as unpriced and excluded from totals."
        )

        return "\n".join(sections)

    @classmethod
    def _render_provider_cost(
        cls,
        *,
        provider: str,
        summary: CostSummary,
    ) -> str:
        return (
            f"\n**{provider.title()}**\n"
            f"Requests: "
            f"`{cls._number(summary.request_count)}`\n"
            f"Successful: "
            f"`{cls._number(summary.successful_requests)}`\n"
            f"Failed: "
            f"`{cls._number(summary.failed_requests)}`\n"
            f"Priced: "
            f"`{cls._number(summary.priced_requests)}`\n"
            f"Unpriced: "
            f"`{cls._number(summary.unpriced_requests)}`\n"
            f"Input tokens: "
            f"`{cls._number(summary.input_tokens)}`\n"
            f"Cached input: "
            f"`{cls._number(summary.cached_input_tokens)}`\n"
            f"Output tokens: "
            f"`{cls._number(summary.output_tokens)}`\n"
            f"Input cost USD: "
            f"`${cls._usd(summary.input_cost_usd)}`\n"
            f"Cached cost USD: "
            f"`${cls._usd(summary.cached_input_cost_usd)}`\n"
            f"Output cost USD: "
            f"`${cls._usd(summary.output_cost_usd)}`\n"
            f"Estimated USD: "
            f"`${cls._usd(summary.total_cost_usd)}`\n"
            f"Estimated INR: "
            f"`₹{cls._inr(summary.total_cost_inr)}`"
        )

    @classmethod
    def _render_total_cost(
        cls,
        summary: CostSummary,
    ) -> str:
        success_average = Decimal("0")

        if summary.successful_requests:
            success_average = (
                summary.total_cost_inr
                / Decimal(
                    summary.successful_requests
                )
            )

        return (
            "\n**Overall Estimated Cost**\n"
            f"Requests: "
            f"`{cls._number(summary.request_count)}`\n"
            f"Priced requests: "
            f"`{cls._number(summary.priced_requests)}`\n"
            f"Unpriced requests: "
            f"`{cls._number(summary.unpriced_requests)}`\n"
            f"Total tokens: "
            f"`{cls._number(summary.total_tokens)}`\n"
            f"Input cost USD: "
            f"`${cls._usd(summary.input_cost_usd)}`\n"
            f"Cached cost USD: "
            f"`${cls._usd(summary.cached_input_cost_usd)}`\n"
            f"Output cost USD: "
            f"`${cls._usd(summary.output_cost_usd)}`\n"
            f"Total USD: "
            f"`${cls._usd(summary.total_cost_usd)}`\n"
            f"Total INR: "
            f"`₹{cls._inr(summary.total_cost_inr)}`\n"
            f"Average INR/request: "
            f"`₹{cls._inr(summary.average_cost_inr_per_request)}`\n"
            f"Average INR/successful request: "
            f"`₹{cls._inr(success_average)}`"
        )

    def _render(
        self,
        *,
        period: str,
        provider: str,
        provider_summaries: dict[
            str,
            TokenUsageSummary,
        ],
        provider_costs: dict[
            str,
            CostSummary,
        ],
        overall: TokenUsageSummary,
        overall_cost: CostSummary,
        generated_at: datetime,
    ) -> str:
        title = self._period_title(
            period
        )

        sections: list[str] = [
            "**Atlas AI Token Usage**",
            f"Period: `{title}`",
            (
                "Provider filter: "
                f"`{provider}`"
            ),
            (
                "Generated: "
                f"`{generated_at.isoformat()}`"
            ),
        ]

        ordered_providers = [
            item
            for item in (
                "openai",
                "gemini",
            )
            if item in provider_summaries
        ]

        additional_providers = sorted(
            set(provider_summaries)
            - set(ordered_providers)
        )

        for provider_name in (
            ordered_providers
            + additional_providers
        ):
            summary = (
                provider_summaries[
                    provider_name
                ]
            )

            cost = provider_costs.get(
                provider_name,
                self.pricing_engine.summarize(
                    []
                ),
            )

            sections.append(
                self._render_provider(
                    provider=provider_name,
                    summary=summary,
                    cost=cost,
                )
            )

        if not provider_summaries:
            sections.append(
                "\nNo provider usage records "
                "were found for this period."
            )

        sections.append(
            self._render_overall(
                summary=overall,
                cost=overall_cost,
            )
        )

        sections.append(
            "\n**Pricing Notes**\n"
            "- Cost is an estimate, not the final card invoice.\n"
            "- USD/INR rate: "
            f"`1 USD = ₹{overall_cost.usd_inr_rate:.4f}`\n"
            "- Failed API calls are counted as requests "
            "but may report zero tokens and zero cost.\n"
            "- Unpriced model calls are excluded from "
            "estimated cost and shown in the unpriced count.\n"
            "- Historic calls made before token metering "
            "was enabled are unavailable."
        )

        return "\n".join(sections)

    @classmethod
    def _render_provider(
        cls,
        *,
        provider: str,
        summary: TokenUsageSummary,
        cost: CostSummary,
    ) -> str:
        return (
            f"\n**{provider.title()}**\n"
            f"Requests: "
            f"`{cls._number(summary.request_count)}`\n"
            f"Successful: "
            f"`{cls._number(summary.successful_requests)}`\n"
            f"Failed: "
            f"`{cls._number(summary.failed_requests)}`\n"
            f"Input tokens: "
            f"`{cls._number(summary.input_tokens)}`\n"
            f"Output tokens: "
            f"`{cls._number(summary.output_tokens)}`\n"
            f"Total tokens: "
            f"`{cls._number(summary.total_tokens)}`\n"
            f"Cached input: "
            f"`{cls._number(summary.cached_input_tokens)}`\n"
            f"Reasoning/thoughts: "
            f"`{cls._number(summary.reasoning_tokens)}`\n"
            f"Tool tokens: "
            f"`{cls._number(summary.tool_tokens)}`\n"
            f"Average latency: "
            f"`{summary.average_latency_ms:,.1f} ms`\n"
            f"Priced requests: "
            f"`{cls._number(cost.priced_requests)}`\n"
            f"Unpriced requests: "
            f"`{cls._number(cost.unpriced_requests)}`\n"
            f"Estimated USD: "
            f"`${cls._usd(cost.total_cost_usd)}`\n"
            f"Estimated INR: "
            f"`₹{cls._inr(cost.total_cost_inr)}`"
        )

    @classmethod
    def _render_overall(
        cls,
        *,
        summary: TokenUsageSummary,
        cost: CostSummary,
    ) -> str:
        average_tokens = (
            summary.total_tokens
            / summary.request_count
            if summary.request_count
            else 0.0
        )

        success_rate = (
            (
                summary.successful_requests
                / summary.request_count
            )
            * 100
            if summary.request_count
            else 0.0
        )

        return (
            "\n**Overall**\n"
            f"Requests: "
            f"`{cls._number(summary.request_count)}`\n"
            f"Total tokens: "
            f"`{cls._number(summary.total_tokens)}`\n"
            f"Average tokens/request: "
            f"`{average_tokens:,.1f}`\n"
            f"Success rate: "
            f"`{success_rate:,.1f}%`\n"
            f"Average latency: "
            f"`{summary.average_latency_ms:,.1f} ms`\n"
            f"Priced requests: "
            f"`{cls._number(cost.priced_requests)}`\n"
            f"Unpriced requests: "
            f"`{cls._number(cost.unpriced_requests)}`\n"
            f"Estimated total USD: "
            f"`${cls._usd(cost.total_cost_usd)}`\n"
            f"Estimated total INR: "
            f"`₹{cls._inr(cost.total_cost_inr)}`\n"
            f"Average INR/request: "
            f"`₹{cls._inr(cost.average_cost_inr_per_request)}`"
        )

    def _validate(
        self,
        *,
        period: str,
        provider: str,
    ) -> str | None:
        if period not in self.VALID_PERIODS:
            return (
                "Invalid usage period. Use "
                "`today`, `week`, `month`, or `all`."
            )

        if provider not in self.VALID_PROVIDERS:
            return (
                "Invalid provider. Use "
                "`all`, `openai`, or `gemini`."
            )

        return None

    @classmethod
    def _filter_records(
        cls,
        *,
        records: list[TokenUsageRecord],
        provider: str,
        since: datetime | None,
    ) -> list[TokenUsageRecord]:
        selected: list[
            TokenUsageRecord
        ] = []

        for record in records:
            if (
                provider != "all"
                and record.provider != provider
            ):
                continue

            if (
                since is not None
                and not cls._record_is_since(
                    record,
                    since,
                )
            ):
                continue

            selected.append(record)

        return selected

    @staticmethod
    def _summaries_by_provider(
        records: list[TokenUsageRecord],
    ) -> dict[str, TokenUsageSummary]:
        providers = sorted(
            {
                record.provider
                for record in records
            }
        )

        return {
            provider: (
                DiscordUsageControls
                ._summarize_tokens(
                    [
                        record
                        for record in records
                        if record.provider
                        == provider
                    ]
                )
            )
            for provider in providers
        }

    @staticmethod
    def _summarize_tokens(
        records: list[TokenUsageRecord],
    ) -> TokenUsageSummary:
        return TokenUsageSummary(
            request_count=len(records),
            successful_requests=sum(
                record.success
                for record in records
            ),
            failed_requests=sum(
                not record.success
                for record in records
            ),
            input_tokens=sum(
                record.input_tokens
                for record in records
            ),
            output_tokens=sum(
                record.output_tokens
                for record in records
            ),
            total_tokens=sum(
                record.total_tokens
                for record in records
            ),
            cached_input_tokens=sum(
                record.cached_input_tokens
                for record in records
            ),
            reasoning_tokens=sum(
                record.reasoning_tokens
                for record in records
            ),
            tool_tokens=sum(
                record.tool_tokens
                for record in records
            ),
            total_latency_ms=sum(
                record.latency_ms
                for record in records
            ),
        )

    @staticmethod
    def _record_is_since(
        record: TokenUsageRecord,
        since: datetime,
    ) -> bool:
        try:
            timestamp = datetime.fromisoformat(
                record.timestamp
            )
        except ValueError:
            return False

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        return timestamp >= since

    @staticmethod
    def _since(
        *,
        period: str,
        now: datetime,
    ) -> datetime | None:
        if period == "all":
            return None

        if period == "week":
            return (
                now
                - timedelta(days=7)
            )

        if period == "month":
            return now.replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

        return now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    def _normalized_now(
        self,
    ) -> datetime:
        now = self.now_provider()

        if now.tzinfo is None:
            return now.replace(
                tzinfo=timezone.utc
            )

        return now.astimezone(
            timezone.utc
        )

    @staticmethod
    def _period_title(
        period: str,
    ) -> str:
        labels = {
            "today": "Today (UTC)",
            "week": "Rolling 7 days",
            "month": "Current month (UTC)",
            "all": "All retained history",
        }

        return labels[period]

    @staticmethod
    def _number(
        value: int,
    ) -> str:
        return f"{value:,}"

    @staticmethod
    def _usd(
        value: Decimal,
    ) -> str:
        return f"{value:.6f}"

    @staticmethod
    def _inr(
        value: Decimal,
    ) -> str:
        return f"{value:.4f}"


__all__ = [
    "DiscordUsageControls",
    "UsageControlResult",
]
