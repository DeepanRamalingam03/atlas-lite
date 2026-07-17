from __future__ import annotations

import asyncio
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace

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
from run_discord_bot import (
    DATA_ROOT,
    build_usage_controls,
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


class DiscordUsageBotWiringTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_usage_bot_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.ledger = TokenUsageLedger(
            self.root / "usage.json"
        )

        self.controls = DiscordUsageControls(
            ledger=self.ledger
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

    def test_usage_command_is_registered(
        self,
    ) -> None:
        command = self.bot.get_command(
            "usage"
        )

        self.assertIsNotNone(command)

    def test_existing_commands_remain_registered(
        self,
    ) -> None:
        expected_commands = {
            "ping",
            "status",
            "ask",
            "reset",
            "runtime",
            "roadmap",
            "workflow",
            "heartbeat",
            "alerts",
            "ackalerts",
            "addtask",
            "pause",
            "resume",
            "usage",
        }

        registered = {
            command.name
            for command in self.bot.commands
        }

        self.assertTrue(
            expected_commands.issubset(
                registered
            )
        )

    def test_usage_command_defaults_to_today(
        self,
    ) -> None:
        context = FakeContext()

        command = self.bot.get_command(
            "usage"
        )

        if command is None:
            self.fail(
                "Usage command was not registered."
            )

        asyncio.run(
            command.callback(
                context
            )
        )

        self.assertEqual(
            len(context.messages),
            1,
        )

        self.assertIn(
            "Today (UTC)",
            context.messages[0],
        )

        self.assertIn(
            "Requests: `0`",
            context.messages[0],
        )

    def test_usage_command_provider_filter(
        self,
    ) -> None:
        self.ledger.append(
            TokenUsageRecord.create(
                provider="openai",
                model="gpt-test",
                success=True,
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            )
        )

        context = FakeContext()

        command = self.bot.get_command(
            "usage"
        )

        if command is None:
            self.fail(
                "Usage command was not registered."
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
            "Total tokens: `15`",
            message,
        )

        self.assertNotIn(
            "**Gemini**",
            message,
        )

    def test_usage_help_command(
        self,
    ) -> None:
        context = FakeContext()

        command = self.bot.get_command(
            "usage"
        )

        if command is None:
            self.fail(
                "Usage command was not registered."
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
            "Atlas AI Usage Commands",
            message,
        )

        self.assertIn(
            "!usage week",
            message,
        )

    def test_bot_uses_injected_controls(
        self,
    ) -> None:
        self.assertIs(
            self.bot.usage_controls,
            self.controls,
        )

    def test_production_builder_uses_data_root(
        self,
    ) -> None:
        controls = build_usage_controls()

        self.assertIsInstance(
            controls,
            DiscordUsageControls,
        )

        expected_path = (
            DATA_ROOT
            / "ai_token_usage.json"
        )

        self.assertEqual(
            controls.ledger.storage_path,
            expected_path,
        )


if __name__ == "__main__":
    unittest.main()
