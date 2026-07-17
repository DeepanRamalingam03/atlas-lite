from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from core.orchestration.roadmap import (
    RoadmapTaskStore,
)
from core.projects.project_runner import (
    ProjectDefinitionError,
    ProjectFolderRunner,
)


class ProjectFolderRunnerTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_project_runner_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(
                self.root
            )

        self.projects_root = (
            self.root
            / "atlas_projects"
        )

        self.data_root = (
            self.root
            / ".atlas_data"
        )

        self.store = RoadmapTaskStore(
            self.data_root
            / "roadmap_tasks.json"
        )

        self.runner = (
            ProjectFolderRunner(
                roadmap_store=self.store,
                projects_root=(
                    self.projects_root
                ),
            )
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(
                self.root
            )

    def test_imports_dependency_ordered_project(
        self,
    ) -> None:
        self._create_project(
            project_id="core-evolution",
            tasks=[
                self._task(
                    "p36",
                    "Metrics",
                    "Build metrics.",
                ),
                self._task(
                    "p37",
                    "Review Guard",
                    "Build review guard.",
                    depends_on=[
                        "p36"
                    ],
                ),
                self._task(
                    "p38",
                    "Knowledge Index",
                    "Build knowledge index.",
                    depends_on=[
                        "p37"
                    ],
                ),
            ],
        )

        result = (
            self.runner.import_project(
                "core-evolution"
            )
        )

        self.assertEqual(
            result.created_count,
            3,
        )

        tasks = (
            self.store.list_all()
        )

        self.assertEqual(
            [
                task.task_id
                for task in tasks
            ],
            [
                "project-core-evolution-p36",
                "project-core-evolution-p37",
                "project-core-evolution-p38",
            ],
        )

        self.assertEqual(
            tasks[1].depends_on,
            (
                "project-core-evolution-p36",
            ),
        )

        self.assertEqual(
            tasks[2].depends_on,
            (
                "project-core-evolution-p37",
            ),
        )

    def test_reimport_is_idempotent(
        self,
    ) -> None:
        self._create_project(
            project_id="sample-project",
            tasks=[
                self._task(
                    "task-one",
                    "Task One",
                    "Complete task one.",
                )
            ],
        )

        first = (
            self.runner.import_project(
                "sample-project"
            )
        )

        second = (
            self.runner.import_project(
                "sample-project"
            )
        )

        self.assertEqual(
            first.created_count,
            1,
        )

        self.assertEqual(
            second.created_count,
            0,
        )

        self.assertEqual(
            second.existing_count,
            1,
        )

        self.assertEqual(
            len(
                self.store.list_all()
            ),
            1,
        )

    def test_conflicting_existing_task_is_rejected(
        self,
    ) -> None:
        self._create_project(
            project_id="sample-project",
            tasks=[
                self._task(
                    "task-one",
                    "Task One",
                    "Original goal.",
                )
            ],
        )

        self.runner.import_project(
            "sample-project"
        )

        task_path = (
            self.projects_root
            / "sample-project"
            / "tasks"
            / "task-one.json"
        )

        payload = json.loads(
            task_path.read_text(
                encoding="utf-8"
            )
        )

        payload["goal"] = (
            "Changed conflicting goal."
        )

        task_path.write_text(
            json.dumps(
                payload,
                indent=2,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ProjectDefinitionError,
            "conflicts",
        ):
            self.runner.import_project(
                "sample-project"
            )

    def test_forward_dependency_is_rejected(
        self,
    ) -> None:
        self._create_project(
            project_id="invalid-project",
            tasks=[
                self._task(
                    "task-one",
                    "Task One",
                    "Task one.",
                    depends_on=[
                        "task-two"
                    ],
                ),
                self._task(
                    "task-two",
                    "Task Two",
                    "Task two.",
                ),
            ],
        )

        with self.assertRaisesRegex(
            ProjectDefinitionError,
            "forward dependencies",
        ):
            self.runner.load_project(
                "invalid-project"
            )

    def test_missing_dependency_is_rejected(
        self,
    ) -> None:
        self._create_project(
            project_id="invalid-project",
            tasks=[
                self._task(
                    "task-one",
                    "Task One",
                    "Task one.",
                    depends_on=[
                        "missing-task"
                    ],
                )
            ],
        )

        with self.assertRaises(
            ProjectDefinitionError
        ):
            self.runner.load_project(
                "invalid-project"
            )

    def test_duplicate_task_ids_are_rejected(
        self,
    ) -> None:
        project_path = (
            self.projects_root
            / "duplicate-project"
        )

        tasks_path = (
            project_path / "tasks"
        )

        tasks_path.mkdir(
            parents=True
        )

        self._write_json(
            project_path
            / "project.json",
            {
                "project_id": (
                    "duplicate-project"
                ),
                "name": "Duplicate",
                "version": "1.0",
                "description": "Test.",
                "tasks": [
                    "tasks/one.json",
                    "tasks/two.json",
                ],
            },
        )

        self._write_json(
            tasks_path / "one.json",
            self._task(
                "same-task",
                "One",
                "One.",
            ),
        )

        self._write_json(
            tasks_path / "two.json",
            self._task(
                "same-task",
                "Two",
                "Two.",
            ),
        )

        with self.assertRaisesRegex(
            ProjectDefinitionError,
            "duplicate task IDs",
        ):
            self.runner.load_project(
                "duplicate-project"
            )

    def test_task_path_traversal_is_rejected(
        self,
    ) -> None:
        project_path = (
            self.projects_root
            / "unsafe-project"
        )

        project_path.mkdir(
            parents=True
        )

        self._write_json(
            project_path
            / "project.json",
            {
                "project_id": (
                    "unsafe-project"
                ),
                "name": "Unsafe",
                "version": "1.0",
                "description": "Unsafe.",
                "tasks": [
                    "../outside.json"
                ],
            },
        )

        with self.assertRaises(
            ProjectDefinitionError
        ):
            self.runner.load_project(
                "unsafe-project"
            )

    def test_project_name_traversal_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ProjectDefinitionError
        ):
            self.runner.load_project(
                "../outside"
            )

    def test_task_limit_is_enforced(
        self,
    ) -> None:
        runner = ProjectFolderRunner(
            roadmap_store=self.store,
            projects_root=(
                self.projects_root
            ),
            max_tasks=2,
        )

        self._create_project(
            project_id="large-project",
            tasks=[
                self._task(
                    "one",
                    "One",
                    "One.",
                ),
                self._task(
                    "two",
                    "Two",
                    "Two.",
                ),
                self._task(
                    "three",
                    "Three",
                    "Three.",
                ),
            ],
        )

        with self.assertRaisesRegex(
            ProjectDefinitionError,
            "task limit",
        ):
            runner.load_project(
                "large-project"
            )

    def test_preview_contains_dependencies(
        self,
    ) -> None:
        self._create_project(
            project_id="preview-project",
            tasks=[
                self._task(
                    "one",
                    "One",
                    "One.",
                ),
                self._task(
                    "two",
                    "Two",
                    "Two.",
                    depends_on=[
                        "one"
                    ],
                ),
            ],
        )

        preview = self.runner.preview(
            "preview-project"
        )

        self.assertIn(
            "Atlas Project Preview",
            preview,
        )

        self.assertIn(
            "preview-project",
            preview,
        )

        self.assertIn(
            "Depends on: `one`",
            preview,
        )

    def test_import_rolls_back_on_failure(
        self,
    ) -> None:
        self._create_project(
            project_id="rollback-project",
            tasks=[
                self._task(
                    "one",
                    "One",
                    "One.",
                ),
                self._task(
                    "two",
                    "Two",
                    "Two.",
                    depends_on=[
                        "one"
                    ],
                ),
            ],
        )

        original_create = (
            self.store.create
        )

        call_count = 0

        def failing_create(
            *args,
            **kwargs,
        ):
            nonlocal call_count
            call_count += 1

            if call_count == 2:
                raise RuntimeError(
                    "Injected failure."
                )

            return original_create(
                *args,
                **kwargs,
            )

        self.store.create = (
            failing_create
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Injected failure",
        ):
            self.runner.import_project(
                "rollback-project"
            )

        self.assertEqual(
            self.store.list_all(),
            [],
        )

    def _create_project(
        self,
        *,
        project_id: str,
        tasks: list[dict],
    ) -> None:
        project_path = (
            self.projects_root
            / project_id
        )

        tasks_path = (
            project_path / "tasks"
        )

        tasks_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        task_files: list[str] = []

        for task in tasks:
            filename = (
                f"{task['task_id']}.json"
            )

            relative = (
                f"tasks/{filename}"
            )

            task_files.append(
                relative
            )

            self._write_json(
                tasks_path / filename,
                task,
            )

        self._write_json(
            project_path
            / "project.json",
            {
                "project_id": project_id,
                "name": (
                    project_id.replace(
                        "-",
                        " ",
                    ).title()
                ),
                "version": "1.0",
                "description": (
                    "Automated Atlas project."
                ),
                "tasks": task_files,
            },
        )

    @staticmethod
    def _task(
        task_id: str,
        title: str,
        goal: str,
        *,
        depends_on: (
            list[str] | None
        ) = None,
    ) -> dict:
        return {
            "task_id": task_id,
            "title": title,
            "goal": goal,
            "priority": 1,
            "depends_on": (
                depends_on or []
            ),
        }

    @staticmethod
    def _write_json(
        path: Path,
        payload: dict,
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                payload,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
