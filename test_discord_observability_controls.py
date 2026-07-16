from __future__ import annotations

import os
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.orchestration.directive_importer import (
    ArchitectDirectiveStatus,
    ArchitectDirectiveStore,
)
from core.orchestration.observability import (
    RuntimeAlertStore,
    RuntimeHeartbeat,
    RuntimeHeartbeatStore,
)
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStore,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)
from discord_gateway.bot import AtlasDiscordBot
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
)
from run_discord_bot import (
    build_runtime_controls,
)


class DiscordObservabilityControlsTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_discord_observability_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.roadmap_store = RoadmapTaskStore(
            self.root / "roadmap.json"
        )

        self.workflow_store = (
            WorkflowStateStore(
                self.root / "workflows.json"
            )
        )

        self.directive_store = (
            ArchitectDirectiveStore(
                self.root / "directives.json"
            )
        )

        self.heartbeat_store = (
            RuntimeHeartbeatStore(
                self.root / "heartbeat.json"
            )
        )

        self.alert_store = RuntimeAlertStore(
            self.root / "alerts.json"
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
                directive_store=(
                    self.directive_store
                ),
                heartbeat_store=(
                    self.heartbeat_store
                ),
                alert_store=(
                    self.alert_store
                ),
            )
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_healthy_heartbeat_status(
        self,
    ) -> None:
        now = datetime.now(
            timezone.utc
        ).isoformat()

        self.heartbeat_store.save(
            RuntimeHeartbeat(
                service_status="running",
                cycle_count=5,
                last_cycle_status="idle",
                task_id=None,
                message="Runtime is idle.",
                process_id=os.getpid(),
                hostname="test-host",
                started_at=now,
                updated_at=now,
            )
        )

        result = (
            self.controls.heartbeat_status()
        )

        self.assertTrue(result.success)
        self.assertIn(
            "`HEALTHY`",
            result.message,
        )
        self.assertIn(
            "Cycle count: `5`",
            result.message,
        )

    def test_missing_heartbeat(
        self,
    ) -> None:
        result = (
            self.controls.heartbeat_status()
        )

        self.assertFalse(result.success)
        self.assertIn(
            "No heartbeat",
            result.message,
        )

    def test_alert_listing_and_acknowledgement(
        self,
    ) -> None:
        self.alert_store.add(
            severity="critical",
            cycle_status="failed",
            task_id="task-1",
            message="Pipeline failed.",
        )

        listed = (
            self.controls.alerts_status()
        )

        self.assertFalse(listed.success)
        self.assertIn(
            "`CRITICAL`",
            listed.message,
        )
        self.assertIn(
            "`task-1`",
            listed.message,
        )

        acknowledged = (
            self.controls
            .acknowledge_alerts()
        )

        self.assertTrue(
            acknowledged.success
        )
        self.assertIn(
            "`1`",
            acknowledged.message,
        )

        empty = self.controls.alerts_status()

        self.assertTrue(empty.success)
        self.assertIn(
            "No active runtime alerts",
            empty.message,
        )

    def test_add_directive(
        self,
    ) -> None:
        result = self.controls.add_directive(
            title="Build production health command",
            goal=(
                "Add a tested production health "
                "command to Atlas."
            ),
            priority=10,
        )

        self.assertTrue(result.success)

        directives = (
            self.directive_store.list_all()
        )

        self.assertEqual(
            len(directives),
            1,
        )
        self.assertEqual(
            directives[0].status,
            ArchitectDirectiveStatus.PENDING,
        )
        self.assertEqual(
            directives[0].priority,
            10,
        )
        self.assertIn(
            directives[0].directive_id,
            result.message,
        )

    def test_runtime_status_includes_health_data(
        self,
    ) -> None:
        result = (
            self.controls.runtime_status(
                100
            )
        )

        self.assertTrue(result.success)
        self.assertIn(
            "Pending directives",
            result.message,
        )
        self.assertIn(
            "Unacknowledged alerts",
            result.message,
        )
        self.assertIn(
            "Heartbeat",
            result.message,
        )

    def test_add_task_parser(
        self,
    ) -> None:
        parsed = AtlasDiscordBot._parse_add_task(
            "5 | Build feature | "
            "Implement and test the feature"
        )

        self.assertEqual(
            parsed,
            (
                5,
                "Build feature",
                "Implement and test the feature",
            ),
        )

    def test_add_task_parser_rejects_invalid_data(
        self,
    ) -> None:
        invalid_inputs = (
            "missing separators",
            "abc | Title | Goal",
            "-1 | Title | Goal",
            "1 | | Goal",
            "1 | Title | ",
        )

        for value in invalid_inputs:
            with self.subTest(value=value):
                with self.assertRaises(
                    ValueError
                ):
                    AtlasDiscordBot._parse_add_task(
                        value
                    )

    def test_production_builder_wires_new_stores(
        self,
    ) -> None:
        controls = build_runtime_controls()

        self.assertIsInstance(
            controls,
            DiscordRuntimeControls,
        )
        self.assertIsInstance(
            controls.directive_store,
            ArchitectDirectiveStore,
        )
        self.assertIsInstance(
            controls.heartbeat_store,
            RuntimeHeartbeatStore,
        )
        self.assertIsInstance(
            controls.alert_store,
            RuntimeAlertStore,
        )


if __name__ == "__main__":
    unittest.main()
