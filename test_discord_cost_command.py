from __future__ import annotations

import asyncio
import shutil
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from core.usage.pricing_engine import (
    PricingEngine,
)
from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
)
from discord_gateway.bot import (
    AtlasDiscordBot,
)
from discord_gateway.usage_controls import (
    DiscordUsageControls,
)


class FakeAssistant:
    def history_size(
        self,
        user_id: int,
    ) -> int:
        return 0

    def clear_history(
        self,
        user_id: int,
    ) -> None:
        return None


class FakeRuntimeControls:
    pass


class FakeContext:
    def __init__(self) -> None:
        self.author = SimpleNamespace(
            id=123
        )
        self.messages: list[str] = []

    async def send(
        self,
        message: str,
    ) -> None:
        self.messages.append(message)


class DiscordCostCommandTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_cost_command_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.ledger = TokenUsageLedger(
            self.root / "usage.json"
        )

        now = datetime(
            2026,
            7,
            17,
            15,
            0,
            tzinfo=timezone.utc,
        )

        self.controls = DiscordUsageControls(
            ledger=self.ledger,
            pricing_engine=PricingEngine(
                usd_inr_rate=Decimal("100")
            ),
            now_provider=lambda: now,
        )

        self.bot = AtlasDiscordBot(
            guild_id=1,
            channel_id=2,
            allowed_user_id=123,
            assistant=FakeAssistant(),
            runtime_controls=(
                FakeRuntimeControls()
            ),
            usage_controls=self.controls,
        )

    def tearDown(self) -> None:
        asyncio.run(
            self.bot.close()
        )

        if self.root.exists():
            shutil.rmtree(self.root)

    def test_cost_command_is_registered(
        self,
    ) -> None:
        self.assertIsNotNone(
            self.bot.get_command(
                "cost"
            )
        )

    def test_existing_commands_are_preserved(
        self,
    ) -> None:
        commands = {
            command.name
            for command in self.bot.commands
        }

        expected = {
            "ping",
            "status",
            "ask",
            "reset",
            "runtime",
            "roadmap",
            "workflow",
            "heartbeat",
            "usage",
            "cost",
            "alerts",
            "ackalerts",
            "addtask",
            "pause",
            "resume",
        }

        self.assertTrue(
            expected.issubset(commands)
        )

    def test_default_cost_report(
        self,
    ) -> None:
        context = FakeContext()
        command = self.bot.get_command(
            "cost"
        )

        if command is None:
            self.fail(
                "Cost command is missing."
            )

        asyncio.run(
            command.callback(
                context
            )
        )

        message = "\n".join(
            context.messages
        )

        self.assertIn(
            "Atlas AI Estimated Cost",
            message,
        )

        self.assertIn(
            "Today (UTC)",
            message,
        )

        self.assertIn(
            "Total INR: `₹0.0000`",
            message,
        )

    def test_cost_provider_filter(
        self,
    ) -> None:
        self.ledger.append(
            TokenUsageRecord.create(
                provider="openai",
                model="gpt-5.1",
                success=True,
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                total_tokens=2_000_000,
            )
        )

        self.ledger.append(
            TokenUsageRecord.create(
                provider="gemini",
                model="gemini-3.5-flash",
                success=True,
                input_tokens=1_000_000,
                output_tokens=0,
                total_tokens=1_000_000,
            )
        )

        context = FakeContext()
        command = self.bot.get_command(
            "cost"
        )

        if command is None:
            self.fail(
                "Cost command is missing."
            )

        asyncio.run(
            command.callback(
                context,
                "all",
                "openai",
            )
        )

        message = "\n".join(
            context.messages
        )

        self.assertIn(
            "Provider filter: `openai`",
            message,
        )

        self.assertIn(
            "Total USD: `$11.250000`",
            message,
        )

        self.assertIn(
            "Total INR: `₹1125.0000`",
            message,
        )

        self.assertNotIn(
            "**Gemini**",
            message,
        )

    def test_cost_help(
        self,
    ) -> None:
        context = FakeContext()
        command = self.bot.get_command(
            "cost"
        )

        if command is None:
            self.fail(
                "Cost command is missing."
            )

        asyncio.run(
            command.callback(
                context,
                "help",
                "all",
            )
        )

        message = "\n".join(
            context.messages
        )

        self.assertIn(
            "!cost month",
            message,
        )

        self.assertIn(
            "!cost all gemini",
            message,
        )

    def test_invalid_period_returns_message(
        self,
    ) -> None:
        context = FakeContext()
        command = self.bot.get_command(
            "cost"
        )

        if command is None:
            self.fail(
                "Cost command is missing."
            )

        asyncio.run(
            command.callback(
                context,
                "year",
                "all",
            )
        )

        message = "\n".join(
            context.messages
        )

        self.assertIn(
            "Invalid usage period",
            message,
        )


if __name__ == "__main__":
    unittest.main()
