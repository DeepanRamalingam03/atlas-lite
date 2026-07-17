from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageSummary,
)


@dataclass(slots=True, frozen=True)
class UsageControlResult:
    success: bool
    message: str


class DiscordUsageControls:
    """
    Read-only Discord reporting surface for Atlas AI usage.

    Supported periods:
    - today: current UTC calendar day
    - week: rolling seven days
    - all: all retained ledger history

    Supported providers:
    - all
    - openai
    - gemini

    This component never clears or modifies usage records.
    """

    VALID_PERIODS = frozenset(
        {
            "today",
            "week",
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
        now_provider: (
            Callable[[], datetime] | None
        ) = None,
    ) -> None:
        self.ledger = ledger
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

        if (
            selected_period
            not in self.VALID_PERIODS
        ):
            return UsageControlResult(
                success=False,
                message=(
                    "Invalid usage period. Use "
                    "`today`, `week`, or `all`."
                ),
            )

        if (
            selected_provider
            not in self.VALID_PROVIDERS
        ):
            return UsageControlResult(
                success=False,
                message=(
                    "Invalid provider. Use "
                    "`all`, `openai`, or `gemini`."
                ),
            )

        now = self._normalized_now()
        since = self._since(
            period=selected_period,
            now=now,
        )

        if selected_provider == "all":
            provider_summaries = (
                self.ledger
                .summarize_by_provider(
                    since=since
                )
            )
        else:
            provider_summaries = {
                selected_provider: (
                    self.ledger.summarize(
                        provider=(
                            selected_provider
                        ),
                        since=since,
                    )
                )
            }

        overall = self.ledger.summarize(
            provider=(
                None
                if selected_provider == "all"
                else selected_provider
            ),
            since=since,
        )

        message = self._render(
            period=selected_period,
            provider=selected_provider,
            provider_summaries=(
                provider_summaries
            ),
            overall=overall,
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
                "`!usage` - today's usage\n"
                "`!usage today` - today's usage\n"
                "`!usage week` - rolling 7 days\n"
                "`!usage all` - all retained history\n"
                "`!usage today openai`\n"
                "`!usage today gemini`\n"
                "`!usage week openai`\n"
                "`!usage all gemini`\n\n"
                "Token values come from official "
                "provider response metadata. "
                "Prompts and responses are not stored."
            ),
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
        overall: TokenUsageSummary,
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

            sections.append(
                self._render_provider(
                    provider=provider_name,
                    summary=summary,
                )
            )

        if not provider_summaries:
            sections.append(
                "\nNo provider usage records "
                "were found for this period."
            )

        sections.append(
            self._render_overall(
                overall
            )
        )

        sections.append(
            "\nNotes:\n"
            "- Failed API calls are counted as "
            "requests but may report zero tokens.\n"
            "- Cost is not shown yet; Phase 32 "
            "pricing configuration will add it.\n"
            "- Historic calls made before token "
            "metering was enabled are unavailable."
        )

        return "\n".join(sections)

    @classmethod
    def _render_provider(
        cls,
        *,
        provider: str,
        summary: TokenUsageSummary,
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
            f"`{summary.average_latency_ms:,.1f} ms`"
        )

    @classmethod
    def _render_overall(
        cls,
        summary: TokenUsageSummary,
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
            f"`{summary.average_latency_ms:,.1f} ms`"
        )

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
            "all": "All retained history",
        }

        return labels[period]

    @staticmethod
    def _number(
        value: int,
    ) -> str:
        return f"{value:,}"


__all__ = [
    "DiscordUsageControls",
    "UsageControlResult",
]
