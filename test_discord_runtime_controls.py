from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from core.orchestration.models import (
    WorkflowStatus,
)
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
)


class DiscordRuntimeControlsTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_controls_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(
            parents=True
        )

        self.roadmap_store = (
            RoadmapTaskStore(
                self.root / "roadmap.json"
            )
        )

        self.workflow_store = (
            WorkflowStateStore(
                self.root / "workflows.json"
            )
        )

        self.controls = (
            DiscordRuntimeControls(
                roadmap_store=(
                    self.roadmap_store
                ),
                workflow_store=(
                    self.workflow_store
                ),
                roadmap_selector=(
                    RoadmapTaskSelector(
                        self.roadmap_store
                    )
                ),
            )
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_empty_runtime_status(
        self,
    ) -> None:
        result = (
            self.controls.runtime_status(
                100
            )
        )

        self.assertTrue(
            result.success
        )
        self.assertIn(
            "Roadmap tasks: `0`",
            result.message,
        )
        self.assertIn(
            "will not create random work",
            result.message,
        )

    def test_roadmap_status_lists_tasks(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Build Discord control",
            goal="Build Discord control",
            priority=10,
            task_id="discord-control",
        )

        result = (
            self.controls.roadmap_status()
        )

        self.assertTrue(
            result.success
        )
        self.assertIn(
            "`discord-control`",
            result.message,
        )
        self.assertIn(
            "[pending]",
            result.message,
        )

    def test_workflow_status(
        self,
    ) -> None:
        self.workflow_store.create(
            user_id=100,
            goal="Build workflow status",
            workflow_id="workflow-status",
        )

        self.workflow_store.update(
            "workflow-status",
            status=WorkflowStatus.PLANNING,
            summary="Planning workflow.",
        )

        result = (
            self.controls.workflow_status(
                user_id=100
            )
        )

        self.assertTrue(
            result.success
        )
        self.assertIn(
            "`workflow-status`",
            result.message,
        )
        self.assertIn(
            "`planning`",
            result.message,
        )

    def test_missing_workflow(
        self,
    ) -> None:
        result = (
            self.controls.workflow_status(
                user_id=100
            )
        )

        self.assertFalse(
            result.success
        )
        self.assertIn(
            "No matching",
            result.message,
        )

    def test_pause_pending_task(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Pause task",
            goal="Pause task",
            task_id="pause-task",
        )

        result = self.controls.pause_task(
            "pause-task"
        )

        self.assertTrue(
            result.success
        )

        task = self.roadmap_store.require(
            "pause-task"
        )

        self.assertEqual(
            task.status,
            RoadmapTaskStatus.PAUSED,
        )

    def test_resume_paused_task(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Resume task",
            goal="Resume task",
            task_id="resume-task",
        )

        self.roadmap_store.update_status(
            "resume-task",
            RoadmapTaskStatus.PAUSED,
        )

        result = self.controls.resume_task(
            "resume-task"
        )

        self.assertTrue(
            result.success
        )

        task = self.roadmap_store.require(
            "resume-task"
        )

        self.assertEqual(
            task.status,
            RoadmapTaskStatus.PENDING,
        )

    def test_resume_blocked_task(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Blocked task",
            goal="Blocked task",
            task_id="blocked-task",
        )

        self.roadmap_store.update_status(
            "blocked-task",
            RoadmapTaskStatus.BLOCKED,
            blocker_reason=(
                "Human login required."
            ),
        )

        result = self.controls.resume_task(
            "blocked-task"
        )

        self.assertTrue(
            result.success
        )
        self.assertEqual(
            self.roadmap_store.require(
                "blocked-task"
            ).status,
            RoadmapTaskStatus.PENDING,
        )

    def test_completed_task_cannot_pause(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Completed task",
            goal="Completed task",
            task_id="completed-task",
        )

        self.roadmap_store.update_status(
            "completed-task",
            RoadmapTaskStatus.RUNNING,
        )

        self.roadmap_store.update_status(
            "completed-task",
            RoadmapTaskStatus.COMPLETED,
        )

        result = self.controls.pause_task(
            "completed-task"
        )

        self.assertFalse(
            result.success
        )
        self.assertIn(
            "cannot be paused",
            result.message,
        )


if __name__ == "__main__":
    unittest.main()
