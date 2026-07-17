from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from discord_gateway.bot import (
    AtlasDiscordBot,
)
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
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


class DiscordRetryCommandTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_retry_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.store = RoadmapTaskStore(
            self.root / "roadmap.json"
        )

        self.controls = DiscordRuntimeControls(
            roadmap_store=self.store,
            roadmap_selector=(
                RoadmapTaskSelector(
                    self.store
                )
            ),
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_retry_control_resets_exact_task(
        self,
    ) -> None:
        target = self._failed_task(
            "target-task"
        )

        other = self._failed_task(
            "other-task"
        )

        result = self.controls.retry_task(
            target.task_id
        )

        self.assertTrue(result.success)

        self.assertIn(
            "Retry Scheduled",
            result.message,
        )

        self.assertEqual(
            self.store.require(
                target.task_id
            ).status,
            RoadmapTaskStatus.PENDING,
        )

        self.assertEqual(
            self.store.require(
                other.task_id
            ).status,
            RoadmapTaskStatus.FAILED,
        )

    def test_non_failed_task_rejected(
        self,
    ) -> None:
        self.store.create(
            title="Pending task",
            goal="Pending.",
            task_id="pending-task",
        )

        result = self.controls.retry_task(
            "pending-task"
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Only failed",
            result.message,
        )

    def test_retry_command_registered(
        self,
    ) -> None:
        bot = AtlasDiscordBot(
            guild_id=1,
            channel_id=2,
            allowed_user_id=3,
            assistant=FakeAssistant(),
            runtime_controls=(
                self.controls
            ),
        )

        names = {
            command.name
            for command in bot.commands
        }

        self.assertIn(
            "retry",
            names,
        )

        self.assertIn(
            "resume",
            names,
        )

    def _failed_task(
        self,
        task_id: str,
    ):
        task = self.store.create(
            title=task_id,
            goal=f"Goal for {task_id}.",
            task_id=task_id,
        )

        self.store.update_status(
            task.task_id,
            RoadmapTaskStatus.RUNNING,
        )

        return self.store.update_status(
            task.task_id,
            RoadmapTaskStatus.FAILED,
        )


if __name__ == "__main__":
    unittest.main()
