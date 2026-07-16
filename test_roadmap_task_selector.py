from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from core.orchestration.roadmap import (
    RoadmapStoreError,
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)


class RoadmapTaskSelectorTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_roadmap_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.store = RoadmapTaskStore(
            storage_path=(
                self.root / "roadmap.json"
            )
        )

        self.selector = RoadmapTaskSelector(
            self.store
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_empty_roadmap_creates_no_work(
        self,
    ) -> None:
        selection = self.selector.select_next()

        self.assertIsNone(selection.task)
        self.assertTrue(
            selection.roadmap_complete
        )
        self.assertIn(
            "will not create random work",
            selection.message,
        )

    def test_highest_priority_ready_task_selected(
        self,
    ) -> None:
        self.store.create(
            title="Low priority",
            goal="Build low priority task",
            priority=100,
            task_id="low",
        )

        self.store.create(
            title="High priority",
            goal="Build high priority task",
            priority=10,
            task_id="high",
        )

        selection = self.selector.select_next()

        self.assertIsNotNone(selection.task)
        self.assertEqual(
            selection.task.task_id,
            "high",
        )
        self.assertEqual(
            selection.ready_count,
            2,
        )

    def test_sequence_breaks_priority_tie(
        self,
    ) -> None:
        self.store.create(
            title="First",
            goal="First task",
            priority=10,
            task_id="first",
        )

        self.store.create(
            title="Second",
            goal="Second task",
            priority=10,
            task_id="second",
        )

        selection = self.selector.select_next()

        self.assertEqual(
            selection.task.task_id,
            "first",
        )

    def test_dependency_must_complete(
        self,
    ) -> None:
        self.store.create(
            title="Foundation",
            goal="Build foundation",
            priority=100,
            task_id="foundation",
        )

        self.store.create(
            title="Dependent",
            goal="Build dependent feature",
            priority=1,
            depends_on=("foundation",),
            task_id="dependent",
        )

        first_selection = self.selector.select_next()

        self.assertEqual(
            first_selection.task.task_id,
            "foundation",
        )

        self.store.update_status(
            "foundation",
            RoadmapTaskStatus.RUNNING,
        )

        self.store.update_status(
            "foundation",
            RoadmapTaskStatus.COMPLETED,
        )

        second_selection = self.selector.select_next()

        self.assertEqual(
            second_selection.task.task_id,
            "dependent",
        )

    def test_failed_dependency_blocks_task(
        self,
    ) -> None:
        self.store.create(
            title="Foundation",
            goal="Build foundation",
            task_id="foundation",
        )

        self.store.create(
            title="Dependent",
            goal="Build dependent",
            depends_on=("foundation",),
            task_id="dependent",
        )

        self.store.update_status(
            "foundation",
            RoadmapTaskStatus.RUNNING,
        )

        self.store.update_status(
            "foundation",
            RoadmapTaskStatus.FAILED,
        )

        selection = self.selector.select_next()

        self.assertIsNone(selection.task)
        self.assertEqual(
            selection.blocked_count,
            1,
        )
        self.assertFalse(
            selection.roadmap_complete
        )

    def test_start_next_marks_running(
        self,
    ) -> None:
        self.store.create(
            title="Runnable",
            goal="Run this task",
            task_id="runnable",
        )

        selection = self.selector.start_next()

        self.assertIsNotNone(selection.task)
        self.assertEqual(
            selection.task.status,
            RoadmapTaskStatus.RUNNING,
        )

        persisted = self.store.require(
            "runnable"
        )

        self.assertEqual(
            persisted.status,
            RoadmapTaskStatus.RUNNING,
        )

    def test_completed_roadmap_is_complete(
        self,
    ) -> None:
        self.store.create(
            title="Only task",
            goal="Complete only task",
            task_id="only",
        )

        self.store.update_status(
            "only",
            RoadmapTaskStatus.RUNNING,
        )

        self.store.update_status(
            "only",
            RoadmapTaskStatus.COMPLETED,
        )

        selection = self.selector.select_next()

        self.assertIsNone(selection.task)
        self.assertTrue(
            selection.roadmap_complete
        )
        self.assertIn(
            "will not create random work",
            selection.message,
        )

    def test_missing_dependency_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            RoadmapStoreError
        ):
            self.store.create(
                title="Invalid",
                goal="Invalid dependency",
                depends_on=("missing",),
                task_id="invalid",
            )

    def test_duplicate_task_rejected(
        self,
    ) -> None:
        self.store.create(
            title="Original",
            goal="Original goal",
            task_id="duplicate",
        )

        with self.assertRaises(
            RoadmapStoreError
        ):
            self.store.create(
                title="Duplicate",
                goal="Duplicate goal",
                task_id="duplicate",
            )

    def test_invalid_transition_rejected(
        self,
    ) -> None:
        self.store.create(
            title="Transition",
            goal="Transition test",
            task_id="transition",
        )

        with self.assertRaises(
            RoadmapStoreError
        ):
            self.store.update_status(
                "transition",
                RoadmapTaskStatus.COMPLETED,
            )

    def test_blocked_status_requires_reason(
        self,
    ) -> None:
        self.store.create(
            title="Blocked",
            goal="Blocked task",
            task_id="blocked",
        )

        with self.assertRaises(
            ValueError
        ):
            self.store.update_status(
                "blocked",
                RoadmapTaskStatus.BLOCKED,
            )

    def test_persistence_after_restart(
        self,
    ) -> None:
        self.store.create(
            title="Persistent",
            goal="Persist roadmap task",
            priority=20,
            source="architect-directive",
            task_id="persistent",
        )

        reloaded_store = RoadmapTaskStore(
            storage_path=(
                self.root / "roadmap.json"
            )
        )

        task = reloaded_store.require(
            "persistent"
        )

        self.assertEqual(
            task.title,
            "Persistent",
        )
        self.assertEqual(
            task.priority,
            20,
        )
        self.assertEqual(
            task.source,
            "architect-directive",
        )

    def test_task_with_dependents_cannot_be_deleted(
        self,
    ) -> None:
        self.store.create(
            title="Parent",
            goal="Parent task",
            task_id="parent",
        )

        self.store.create(
            title="Child",
            goal="Child task",
            depends_on=("parent",),
            task_id="child",
        )

        with self.assertRaises(
            RoadmapStoreError
        ):
            self.store.delete("parent")


if __name__ == "__main__":
    unittest.main()
