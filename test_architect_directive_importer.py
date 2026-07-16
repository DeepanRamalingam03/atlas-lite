from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.orchestration.autonomy_policy import (
    AutonomyPolicy,
)
from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
)
from core.orchestration.directive_importer import (
    ArchitectDirectiveStatus,
    ArchitectDirectiveStore,
    ArchitectDirectiveStoreError,
    RoadmapDirectiveImporter,
)
from core.orchestration.directive_runtime import (
    DirectiveAwareRuntimeService,
)
from core.orchestration.recovery_manager import (
    WorkflowRecoveryManager,
)
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from core.orchestration.runtime_lock import (
    RuntimeProcessLock,
)
from core.orchestration.runtime_service import (
    RuntimeCycleStatus,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)


class FakePipeline:
    def execute(self, goal: str):
        return SimpleNamespace(
            approved=True,
            file_changes=[
                SimpleNamespace(
                    path="core/imported_feature.py"
                )
            ],
            manager_review="DECISION: APPROVED",
            test_result=SimpleNamespace(
                combined_output="Tests passed"
            ),
        )


class FakeReleaseCoordinator:
    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan=None,
    ):
        return SimpleNamespace(
            success=True,
            error=None,
        )


class ArchitectDirectiveImporterTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_directive_importer_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.directive_store = (
            ArchitectDirectiveStore(
                self.root / "directives.json"
            )
        )

        self.roadmap_store = RoadmapTaskStore(
            self.root / "roadmap.json"
        )

        self.importer = RoadmapDirectiveImporter(
            directive_store=(
                self.directive_store
            ),
            roadmap_store=self.roadmap_store,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_pending_directive_is_imported(
        self,
    ) -> None:
        self.directive_store.create(
            title="Build importer",
            goal="Build architect importer",
            priority=5,
            directive_id="phase-25",
        )

        result = self.importer.import_pending()

        self.assertEqual(
            result.imported_count,
            1,
        )
        self.assertEqual(
            result.failed_count,
            0,
        )

        directive = self.directive_store.require(
            "phase-25"
        )

        self.assertEqual(
            directive.status,
            ArchitectDirectiveStatus.IMPORTED,
        )

        task = self.roadmap_store.require(
            "directive-task-phase-25"
        )

        self.assertEqual(
            task.title,
            "Build importer",
        )
        self.assertEqual(task.priority, 5)

    def test_import_is_idempotent(
        self,
    ) -> None:
        self.directive_store.create(
            title="Idempotent",
            goal="Idempotent import",
            directive_id="idempotent",
        )

        first = self.importer.import_pending()
        second = self.importer.import_pending()

        self.assertEqual(
            first.imported_count,
            1,
        )
        self.assertEqual(
            second.imported_count,
            0,
        )
        self.assertEqual(
            len(self.roadmap_store.list_all()),
            1,
        )

    def test_missing_dependency_marks_failed(
        self,
    ) -> None:
        self.directive_store.create(
            title="Dependent",
            goal="Dependent task",
            depends_on=("missing-task",),
            directive_id="dependent",
        )

        result = self.importer.import_pending()

        self.assertEqual(
            result.failed_count,
            1,
        )

        directive = self.directive_store.require(
            "dependent"
        )

        self.assertEqual(
            directive.status,
            ArchitectDirectiveStatus.FAILED,
        )
        self.assertIn(
            "missing",
            directive.error or "",
        )

    def test_failed_directive_can_retry(
        self,
    ) -> None:
        self.directive_store.create(
            title="Retry",
            goal="Retry directive",
            depends_on=("foundation",),
            directive_id="retry",
        )

        self.importer.import_pending()

        self.roadmap_store.create(
            title="Foundation",
            goal="Foundation",
            task_id="foundation",
        )

        self.directive_store.retry("retry")

        result = self.importer.import_pending()

        self.assertEqual(
            result.imported_count,
            1,
        )

    def test_duplicate_directive_rejected(
        self,
    ) -> None:
        self.directive_store.create(
            title="First",
            goal="First",
            directive_id="duplicate",
        )

        with self.assertRaises(
            ArchitectDirectiveStoreError
        ):
            self.directive_store.create(
                title="Second",
                goal="Second",
                directive_id="duplicate",
            )

    def test_directive_runtime_imports_and_executes(
        self,
    ) -> None:
        workflow_store = WorkflowStateStore(
            self.root / "workflows.json"
        )

        orchestrator = ContinuousOrchestrator(
            pipeline=FakePipeline(),
            release_coordinator=(
                FakeReleaseCoordinator()
            ),
            workflow_store=workflow_store,
            autonomy_policy=AutonomyPolicy(
                development_branches={"main"}
            ),
            branch="main",
            push=False,
        )

        recovery = WorkflowRecoveryManager(
            orchestrator=orchestrator,
            workflow_store=workflow_store,
        )

        service = DirectiveAwareRuntimeService(
            roadmap_store=self.roadmap_store,
            roadmap_selector=RoadmapTaskSelector(
                self.roadmap_store
            ),
            orchestrator=orchestrator,
            recovery_manager=recovery,
            process_lock=RuntimeProcessLock(
                self.root / "runtime.lock"
            ),
            user_id=100,
            idle_seconds=0,
            directive_importer=self.importer,
        )

        self.directive_store.create(
            title="Runtime directive",
            goal="Execute imported directive",
            directive_id="runtime",
        )

        result = service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.COMPLETED,
        )

        task = self.roadmap_store.require(
            "directive-task-runtime"
        )

        self.assertEqual(
            task.status,
            RoadmapTaskStatus.COMPLETED,
        )

        self.assertIsNotNone(
            service.last_import_result
        )
        self.assertEqual(
            service.last_import_result.imported_count,
            1,
        )


if __name__ == "__main__":
    unittest.main()
