from __future__ import annotations

import os
import shutil
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.orchestration.observability import (
    RuntimeAlertStore,
    RuntimeDiskCleaner,
    RuntimeHeartbeatStore,
    RuntimeObserver,
)
from core.orchestration.runtime_lock import (
    RuntimeProcessLock,
)
from core.orchestration.runtime_service import (
    RuntimeCycleResult,
    RuntimeCycleStatus,
)
from run_continuous_runtime import (
    build_runtime_observer,
    build_runtime_service,
)


class RuntimeObservabilityTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_observability_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.heartbeat_store = (
            RuntimeHeartbeatStore(
                self.root / "heartbeat.json"
            )
        )

        self.alert_store = RuntimeAlertStore(
            self.root / "alerts.json",
            max_alerts=3,
        )

        self.cleanup_root = (
            self.root / "cleanup"
        )
        self.cleanup_root.mkdir()

        self.cleaner = RuntimeDiskCleaner(
            roots=(self.cleanup_root,),
            minimum_age_seconds=10,
        )

        self.observer = RuntimeObserver(
            heartbeat_store=(
                self.heartbeat_store
            ),
            alert_store=self.alert_store,
            disk_cleaner=self.cleaner,
            cleanup_interval_cycles=2,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_started_heartbeat(
        self,
    ) -> None:
        heartbeat = (
            self.observer.mark_started()
        )

        self.assertEqual(
            heartbeat.service_status,
            "running",
        )
        self.assertEqual(
            heartbeat.cycle_count,
            0,
        )

        persisted = (
            self.heartbeat_store.load()
        )

        self.assertIsNotNone(persisted)
        self.assertEqual(
            persisted.process_id,
            os.getpid(),
        )

    def test_cycle_updates_heartbeat(
        self,
    ) -> None:
        result = RuntimeCycleResult(
            status=RuntimeCycleStatus.IDLE,
            roadmap_selection=None,
            roadmap_task=None,
            workflow_result=None,
            resumed=False,
            message="No work available.",
        )

        heartbeat = (
            self.observer.handle_cycle(
                result
            )
        )

        self.assertEqual(
            heartbeat.cycle_count,
            1,
        )
        self.assertEqual(
            heartbeat.last_cycle_status,
            "idle",
        )
        self.assertEqual(
            heartbeat.message,
            "No work available.",
        )

    def test_failure_creates_alert(
        self,
    ) -> None:
        task = SimpleNamespace(
            task_id="failed-task"
        )

        result = RuntimeCycleResult(
            status=RuntimeCycleStatus.FAILED,
            roadmap_selection=None,
            roadmap_task=task,
            workflow_result=None,
            resumed=False,
            message="Permanent failure.",
        )

        self.observer.handle_cycle(
            result
        )

        alerts = (
            self.alert_store
            .list_unacknowledged()
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].severity,
            "critical",
        )
        self.assertEqual(
            alerts[0].task_id,
            "failed-task",
        )

    def test_human_blocker_creates_warning(
        self,
    ) -> None:
        result = RuntimeCycleResult(
            status=(
                RuntimeCycleStatus
                .WAITING_FOR_HUMAN
            ),
            roadmap_selection=None,
            roadmap_task=SimpleNamespace(
                task_id="human-task"
            ),
            workflow_result=None,
            resumed=False,
            message="MFA required.",
        )

        self.observer.handle_cycle(
            result
        )

        alerts = (
            self.alert_store
            .list_unacknowledged()
        )

        self.assertEqual(
            alerts[0].severity,
            "warning",
        )

    def test_alert_store_is_bounded(
        self,
    ) -> None:
        for index in range(5):
            self.alert_store.add(
                severity="warning",
                cycle_status="failed",
                task_id=str(index),
                message=f"Alert {index}",
            )

        alerts = (
            self.alert_store.list_all()
        )

        self.assertEqual(
            len(alerts),
            3,
        )
        self.assertEqual(
            alerts[-1].message,
            "Alert 4",
        )

    def test_acknowledge_all(
        self,
    ) -> None:
        self.alert_store.add(
            severity="warning",
            cycle_status="failed",
            task_id="task",
            message="Failure",
        )

        changed = (
            self.alert_store
            .acknowledge_all()
        )

        self.assertEqual(changed, 1)
        self.assertEqual(
            self.alert_store
            .list_unacknowledged(),
            [],
        )

    def test_disk_cleanup_removes_only_stale_children(
        self,
    ) -> None:
        stale_file = (
            self.cleanup_root
            / "stale.txt"
        )
        fresh_file = (
            self.cleanup_root
            / "fresh.txt"
        )
        stale_directory = (
            self.cleanup_root
            / "old-directory"
        )

        stale_file.write_text(
            "stale",
            encoding="utf-8",
        )
        fresh_file.write_text(
            "fresh",
            encoding="utf-8",
        )
        stale_directory.mkdir()

        (
            stale_directory / "data.txt"
        ).write_text(
            "old",
            encoding="utf-8",
        )

        old_timestamp = time.time() - 100

        os.utime(
            stale_file,
            (
                old_timestamp,
                old_timestamp,
            ),
        )
        os.utime(
            stale_directory,
            (
                old_timestamp,
                old_timestamp,
            ),
        )

        result = self.cleaner.cleanup(
            now_timestamp=time.time()
        )

        self.assertFalse(
            stale_file.exists()
        )
        self.assertFalse(
            stale_directory.exists()
        )
        self.assertTrue(
            fresh_file.exists()
        )
        self.assertTrue(
            self.cleanup_root.exists()
        )
        self.assertEqual(
            result.removed_files,
            1,
        )
        self.assertEqual(
            result.removed_directories,
            1,
        )

    def test_runtime_callback_is_immediate_and_bounded(
        self,
    ) -> None:
        observed: list[str] = []

        service = build_runtime_service()

        service.process_lock = RuntimeProcessLock(
            self.root / "callback-runtime.lock"
        )

        service.cycle_callback = (
            lambda result: observed.append(
                result.status.value
            )
        )

        service.history_limit = 2
        service.idle_seconds = 0

        results = service.run_forever(
            max_cycles=4
        )

        self.assertEqual(
            len(observed),
            4,
        )
        self.assertEqual(
            len(results),
            2,
        )
        self.assertEqual(
            observed,
            [
                "idle",
                "idle",
                "idle",
                "idle",
            ],
        )
        self.assertFalse(
            service.process_lock.acquired
        )

    def test_entrypoint_observer_builds(
        self,
    ) -> None:
        observer = (
            build_runtime_observer()
        )

        self.assertIsInstance(
            observer,
            RuntimeObserver,
        )


if __name__ == "__main__":
    unittest.main()
