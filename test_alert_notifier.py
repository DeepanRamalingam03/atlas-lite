from __future__ import annotations

import shutil
import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

from core.orchestration.observability import (
    RuntimeAlertStore,
    RuntimeHeartbeat,
    RuntimeHeartbeatStore,
)
from run_alert_notifier import (
    DeliveryStateStore,
    RuntimeAlertNotifier,
)


class AlertNotifierTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_alert_notifier_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.alert_store = RuntimeAlertStore(
            self.root / "alerts.json"
        )

        self.heartbeat_store = (
            RuntimeHeartbeatStore(
                self.root / "heartbeat.json"
            )
        )

        self.delivery_store = (
            DeliveryStateStore(
                self.root / "deliveries.json"
            )
        )

        self.messages: list[str] = []

        self.notifier = RuntimeAlertNotifier(
            alert_store=self.alert_store,
            heartbeat_store=(
                self.heartbeat_store
            ),
            delivery_store=(
                self.delivery_store
            ),
            sender=self.messages.append,
            heartbeat_stale_seconds=60,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_first_poll_sets_baseline_without_fake_recovery(
        self,
    ) -> None:
        self._save_healthy_heartbeat()

        result = self.notifier.poll_once()

        self.assertFalse(
            result.heartbeat_notification_sent
        )
        self.assertEqual(
            self.messages,
            [],
        )

        persisted = (
            self.delivery_store.load()
        )

        self.assertEqual(
            persisted["heartbeat_state"],
            "healthy",
        )

    def test_new_alert_is_sent_once(
        self,
    ) -> None:
        self._save_healthy_heartbeat()
        self.notifier.poll_once()

        self.alert_store.add(
            severity="critical",
            cycle_status="failed",
            task_id="task-1",
            message="Pipeline failed.",
        )

        first = self.notifier.poll_once()
        second = self.notifier.poll_once()

        alert_messages = [
            message
            for message in self.messages
            if "Runtime Alert" in message
        ]

        self.assertEqual(
            first.sent_count,
            1,
        )
        self.assertEqual(
            second.sent_count,
            0,
        )
        self.assertEqual(
            len(alert_messages),
            1,
        )
        self.assertIn(
            "`task-1`",
            alert_messages[0],
        )

    def test_failed_delivery_is_retried(
        self,
    ) -> None:
        attempts = 0

        def failing_once(
            message: str,
        ) -> None:
            nonlocal attempts
            attempts += 1

            if attempts == 1:
                raise RuntimeError(
                    "Temporary network failure"
                )

            self.messages.append(message)

        notifier = RuntimeAlertNotifier(
            alert_store=self.alert_store,
            heartbeat_store=(
                self.heartbeat_store
            ),
            delivery_store=(
                self.delivery_store
            ),
            sender=failing_once,
            heartbeat_stale_seconds=60,
        )

        self._save_healthy_heartbeat()
        notifier.poll_once()

        self.alert_store.add(
            severity="warning",
            cycle_status="failed",
            task_id="retry-task",
            message="Retry alert.",
        )

        first = notifier.poll_once()
        second = notifier.poll_once()

        self.assertEqual(
            first.failed_count,
            1,
        )
        self.assertEqual(
            first.sent_count,
            0,
        )
        self.assertEqual(
            second.sent_count,
            1,
        )
        self.assertEqual(
            len(self.messages),
            1,
        )

    def test_stale_transition_sends_health_alert(
        self,
    ) -> None:
        self._save_healthy_heartbeat()
        self.notifier.poll_once()

        stale_time = (
            datetime.now(timezone.utc)
            - timedelta(minutes=5)
        ).isoformat()

        self.heartbeat_store.save(
            RuntimeHeartbeat(
                service_status="running",
                cycle_count=2,
                last_cycle_status="idle",
                task_id=None,
                message="Idle",
                process_id=1,
                hostname="test",
                started_at=stale_time,
                updated_at=stale_time,
            )
        )

        result = self.notifier.poll_once()

        self.assertTrue(
            result.heartbeat_notification_sent
        )
        self.assertTrue(
            any(
                "Runtime Health Alert" in message
                and "`stale`" in message
                for message in self.messages
            )
        )

    def test_recovery_transition_sends_notification(
        self,
    ) -> None:
        self.delivery_store.save(
            {
                "delivered_alert_ids": [],
                "heartbeat_state": "stale",
            }
        )

        self._save_healthy_heartbeat()

        result = self.notifier.poll_once()

        self.assertTrue(
            result.heartbeat_notification_sent
        )
        self.assertTrue(
            any(
                "Runtime Recovered" in message
                for message in self.messages
            )
        )

    def test_missing_heartbeat_transition_sends_alert(
        self,
    ) -> None:
        self.delivery_store.save(
            {
                "delivered_alert_ids": [],
                "heartbeat_state": "healthy",
            }
        )

        result = self.notifier.poll_once()

        self.assertTrue(
            result.heartbeat_notification_sent
        )
        self.assertTrue(
            any(
                "`missing`" in message
                for message in self.messages
            )
        )

    def test_delivery_state_persists(
        self,
    ) -> None:
        self.delivery_store.save(
            {
                "delivered_alert_ids": [
                    "one",
                    "two",
                ],
                "heartbeat_state": "healthy",
            }
        )

        reloaded = DeliveryStateStore(
            self.root / "deliveries.json"
        ).load()

        self.assertEqual(
            reloaded["delivered_alert_ids"],
            ["one", "two"],
        )
        self.assertEqual(
            reloaded["heartbeat_state"],
            "healthy",
        )

    def test_delivery_store_is_bounded(
        self,
    ) -> None:
        store = DeliveryStateStore(
            self.root / "bounded.json",
            max_ids=2,
        )

        store.save(
            {
                "delivered_alert_ids": [
                    "one",
                    "two",
                    "three",
                ],
                "heartbeat_state": "healthy",
            }
        )

        loaded = store.load()

        self.assertEqual(
            loaded["delivered_alert_ids"],
            ["two", "three"],
        )

    def _save_healthy_heartbeat(
        self,
    ) -> None:
        now = datetime.now(
            timezone.utc
        ).isoformat()

        self.heartbeat_store.save(
            RuntimeHeartbeat(
                service_status="running",
                cycle_count=1,
                last_cycle_status="idle",
                task_id=None,
                message="Runtime is idle.",
                process_id=1,
                hostname="test-host",
                started_at=now,
                updated_at=now,
            )
        )


if __name__ == "__main__":
    unittest.main()
