from __future__ import annotations

import unittest

from discord_gateway.bot import (
    AtlasDiscordBot,
)
from discord_gateway.project_controls import (
    DiscordProjectControls,
)
from run_discord_bot import (
    PROJECT_ROOT,
    build_project_controls,
)


class FakeAssistant:
    def history_size(
        self,
        user_id: int,
    ) -> int:
        return 0

    def ask(
        self,
        user_id: int,
        question: str,
    ) -> str:
        return "unused"

    def clear_history(
        self,
        user_id: int,
    ) -> None:
        return None


class DiscordProjectBotWiringTest(
    unittest.TestCase
):
    def test_commands_registered(
        self,
    ) -> None:
        bot = AtlasDiscordBot(
            guild_id=1,
            channel_id=2,
            allowed_user_id=3,
            assistant=FakeAssistant(),
        )

        names = {
            command.name
            for command in bot.commands
        }

        self.assertIn(
            "project",
            names,
        )

        self.assertIn(
            "runproject",
            names,
        )

        self.assertIn(
            "roadmap",
            names,
        )

    def test_production_builder(
        self,
    ) -> None:
        controls = (
            build_project_controls()
        )

        self.assertIsInstance(
            controls,
            DiscordProjectControls,
        )

        self.assertIsNotNone(
            controls.runner
        )

        assert controls.runner is not None

        self.assertEqual(
            controls.runner.projects_root,
            (
                PROJECT_ROOT
                / "atlas_projects"
            ).resolve(),
        )


if __name__ == "__main__":
    unittest.main()
