from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from core.orchestration.roadmap import (
    RoadmapTaskStore,
)
from core.projects.project_runner import (
    ProjectFolderRunner,
)
from discord_gateway.project_controls import (
    DiscordProjectControls,
)


class DiscordProjectControlsTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_project_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.projects_root = (
            self.root / "atlas_projects"
        )

        self.store = RoadmapTaskStore(
            self.root
            / ".atlas_data"
            / "roadmap_tasks.json"
        )

        self.controls = DiscordProjectControls(
            runner=ProjectFolderRunner(
                roadmap_store=self.store,
                projects_root=(
                    self.projects_root
                ),
            )
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_preview_and_import(
        self,
    ) -> None:
        self._create_project()

        preview = (
            self.controls
            .preview_project(
                "sample-project"
            )
        )

        imported = (
            self.controls
            .run_project(
                "sample-project"
            )
        )

        self.assertTrue(preview.success)
        self.assertTrue(imported.success)

        self.assertIn(
            "Atlas Project Preview",
            preview.message,
        )

        self.assertIn(
            "Created: `2`",
            imported.message,
        )

        tasks = self.store.list_all()

        self.assertEqual(len(tasks), 2)

        self.assertEqual(
            tasks[1].depends_on,
            (
                "project-sample-project-task-one",
            ),
        )

    def test_reimport_is_idempotent(
        self,
    ) -> None:
        self._create_project()

        self.controls.run_project(
            "sample-project"
        )

        second = (
            self.controls.run_project(
                "sample-project"
            )
        )

        self.assertTrue(second.success)

        self.assertIn(
            "Created: `0`",
            second.message,
        )

        self.assertIn(
            "Already existing: `2`",
            second.message,
        )

    def test_missing_project_fails_safely(
        self,
    ) -> None:
        result = (
            self.controls
            .preview_project(
                "missing-project"
            )
        )

        self.assertFalse(result.success)

        self.assertIn(
            "Preview Failed",
            result.message,
        )

    def test_unconfigured_controls_fail(
        self,
    ) -> None:
        controls = (
            DiscordProjectControls()
        )

        result = controls.run_project(
            "sample-project"
        )

        self.assertFalse(result.success)

        self.assertIn(
            "not configured",
            result.message,
        )

    def _create_project(
        self,
    ) -> None:
        project = (
            self.projects_root
            / "sample-project"
        )

        tasks = project / "tasks"

        tasks.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._write(
            project / "project.json",
            {
                "project_id": (
                    "sample-project"
                ),
                "name": "Sample Project",
                "version": "1.0",
                "description": (
                    "Project runner test."
                ),
                "tasks": [
                    "tasks/task-one.json",
                    "tasks/task-two.json",
                ],
            },
        )

        self._write(
            tasks / "task-one.json",
            {
                "task_id": "task-one",
                "title": "Task One",
                "goal": "Complete task one.",
                "priority": 1,
                "depends_on": [],
            },
        )

        self._write(
            tasks / "task-two.json",
            {
                "task_id": "task-two",
                "title": "Task Two",
                "goal": "Complete task two.",
                "priority": 1,
                "depends_on": [
                    "task-one"
                ],
            },
        )

    @staticmethod
    def _write(
        path: Path,
        payload: dict,
    ) -> None:
        path.write_text(
            json.dumps(
                payload,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
