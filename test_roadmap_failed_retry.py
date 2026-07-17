from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from core.orchestration.roadmap import (
    RoadmapStoreError,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)


class RoadmapFailedRetryTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_failed_retry_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.store = RoadmapTaskStore(
            self.root / "roadmap.json"
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_failed_task_returns_to_pending(
        self,
    ) -> None:
        task = self.store.create(
            title="Retry task",
            goal="Retry only this task.",
            task_id="retry-task",
        )

        self.store.update_status(
            task.task_id,
            RoadmapTaskStatus.RUNNING,
        )

        self.store.update_status(
            task.task_id,
            RoadmapTaskStatus.FAILED,
        )

        retried = self.store.retry_failed(
            task.task_id
        )

        self.assertEqual(
            retried.status,
            RoadmapTaskStatus.PENDING,
        )

        self.assertIsNone(
            retried.blocker_reason
        )

    def test_pending_task_cannot_retry(
        self,
    ) -> None:
        self.store.create(
            title="Pending",
            goal="Remain pending.",
            task_id="pending-task",
        )

        with self.assertRaisesRegex(
            RoadmapStoreError,
            "Only failed",
        ):
            self.store.retry_failed(
                "pending-task"
            )

    def test_completed_task_cannot_retry(
        self,
    ) -> None:
        task = self.store.create(
            title="Completed",
            goal="Remain complete.",
            task_id="completed-task",
        )

        self.store.update_status(
            task.task_id,
            RoadmapTaskStatus.RUNNING,
        )

        self.store.update_status(
            task.task_id,
            RoadmapTaskStatus.COMPLETED,
        )

        with self.assertRaises(
            RoadmapStoreError
        ):
            self.store.retry_failed(
                task.task_id
            )

    def test_missing_task_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            KeyError
        ):
            self.store.retry_failed(
                "missing-task"
            )

    def test_other_failed_tasks_are_unchanged(
        self,
    ) -> None:
        first = self.store.create(
            title="First",
            goal="First.",
            task_id="first",
        )

        second = self.store.create(
            title="Second",
            goal="Second.",
            task_id="second",
        )

        for task in (first, second):
            self.store.update_status(
                task.task_id,
                RoadmapTaskStatus.RUNNING,
            )

            self.store.update_status(
                task.task_id,
                RoadmapTaskStatus.FAILED,
            )

        self.store.retry_failed("first")

        self.assertEqual(
            self.store.require(
                "first"
            ).status,
            RoadmapTaskStatus.PENDING,
        )

        self.assertEqual(
            self.store.require(
                "second"
            ).status,
            RoadmapTaskStatus.FAILED,
        )


if __name__ == "__main__":
    unittest.main()
