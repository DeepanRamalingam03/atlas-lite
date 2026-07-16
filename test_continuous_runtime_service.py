from __future__ import annotations

import shutil
import unittest
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from core.orchestration.autonomy_policy import (
    AutonomyPolicy,
)
from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
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
    ContinuousRuntimeService,
    RuntimeCycleStatus,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)


@dataclass(slots=True, frozen=True)
class FakeChange:
    path: str


class FakePipeline:
    def __init__(
        self,
        *,
        approved: bool = True,
        paths: tuple[str, ...] = (
            "core/runtime_generated.py",
        ),
    ) -> None:
        self.approved = approved
        self.paths = paths
        self.calls: list[str] = []

    def execute(self, goal: str):
        self.calls.append(goal)

        return SimpleNamespace(
            approved=self.approved,
            file_changes=[
                FakeChange(path=path)
                for path in self.paths
            ],
            manager_review=(
                "DECISION: APPROVED"
                if self.approved
                else "DECISION: REJECTED"
            ),
            test_result=SimpleNamespace(
                combined_output=(
                    "Tests passed"
                    if self.approved
                    else "Tests failed"
                )
            ),
        )


class FakeReleaseCoordinator:
    def __init__(
        self,
        *,
        success: bool = True,
    ) -> None:
        self.success = success
        self.calls = 0

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan=None,
    ):
        self.calls += 1

        return SimpleNamespace(
            success=self.success,
            error=(
                None
                if self.success
                else "Release failed"
            ),
        )


class ContinuousRuntimeServiceTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_runtime_service_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.roadmap_store = RoadmapTaskStore(
            self.root / "roadmap.json"
        )
        self.roadmap_selector = (
            RoadmapTaskSelector(
                self.roadmap_store
            )
        )
        self.workflow_store = WorkflowStateStore(
            self.root / "workflows.json"
        )
        self.pipeline = FakePipeline()
        self.release = FakeReleaseCoordinator()

        self.orchestrator = ContinuousOrchestrator(
            pipeline=self.pipeline,
            release_coordinator=self.release,
            workflow_store=self.workflow_store,
            autonomy_policy=AutonomyPolicy(
                development_branches={"main"}
            ),
            branch="main",
            push=True,
        )

        self.recovery = WorkflowRecoveryManager(
            orchestrator=self.orchestrator,
            workflow_store=self.workflow_store,
        )

        self.lock = RuntimeProcessLock(
            self.root / "runtime.lock"
        )

        self.sleep_calls: list[float] = []

        self.service = ContinuousRuntimeService(
            roadmap_store=self.roadmap_store,
            roadmap_selector=self.roadmap_selector,
            orchestrator=self.orchestrator,
            recovery_manager=self.recovery,
            process_lock=self.lock,
            user_id=100,
            idle_seconds=0.01,
            sleep_function=self.sleep_calls.append,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_empty_roadmap_is_idle(
        self,
    ) -> None:
        result = self.service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.IDLE,
        )
        self.assertIsNone(
            result.roadmap_task
        )
        self.assertIn(
            "will not create random work",
            result.message,
        )
        self.assertEqual(
            len(self.pipeline.calls),
            0,
        )

    def test_ready_task_completes(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Build runtime feature",
            goal="Build tested runtime feature",
            task_id="runtime-feature",
        )

        result = self.service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.COMPLETED,
        )
        self.assertEqual(
            result.roadmap_task.status,
            RoadmapTaskStatus.COMPLETED,
        )
        self.assertTrue(
            result.workflow_result.completed
        )
        self.assertEqual(
            len(self.pipeline.calls),
            1,
        )
        self.assertEqual(
            self.release.calls,
            1,
        )

    def test_constitution_task_becomes_blocked(
        self,
    ) -> None:
        self.pipeline.paths = (
            "atlas_core/constitution/ROADMAP.md",
        )

        self.roadmap_store.create(
            title="Change constitution",
            goal="Change constitution roadmap",
            task_id="constitution-task",
        )

        result = self.service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.WAITING_FOR_HUMAN,
        )
        self.assertEqual(
            result.roadmap_task.status,
            RoadmapTaskStatus.BLOCKED,
        )
        self.assertEqual(
            self.release.calls,
            0,
        )

    def test_pipeline_failure_marks_task_failed(
        self,
    ) -> None:
        self.pipeline.approved = False

        self.roadmap_store.create(
            title="Failing task",
            goal="Build failing task",
            task_id="failing-task",
        )

        result = self.service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.FAILED,
        )
        self.assertEqual(
            result.roadmap_task.status,
            RoadmapTaskStatus.FAILED,
        )
        self.assertEqual(
            self.release.calls,
            0,
        )

    def test_running_task_is_resumed(
        self,
    ) -> None:
        task = self.roadmap_store.create(
            title="Interrupted task",
            goal="Resume interrupted task",
            task_id="interrupted-task",
        )

        self.roadmap_store.update_status(
            task.task_id,
            RoadmapTaskStatus.RUNNING,
        )

        workflow_id = (
            self.service._workflow_id(
                task.task_id
            )
        )

        self.workflow_store.create(
            user_id=100,
            goal=task.goal,
            workflow_id=workflow_id,
        )

        self.workflow_store.update(
            workflow_id,
            status=(
                __import__(
                    "core.orchestration.models",
                    fromlist=["WorkflowStatus"],
                ).WorkflowStatus.PLANNING
            ),
        )

        result = self.service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.COMPLETED,
        )
        self.assertTrue(
            result.resumed
        )
        self.assertEqual(
            result.roadmap_task.status,
            RoadmapTaskStatus.COMPLETED,
        )

    def test_run_forever_uses_process_lock(
        self,
    ) -> None:
        stop_event = Event()

        results = self.service.run_forever(
            stop_event=stop_event,
            max_cycles=2,
        )

        self.assertEqual(
            len(results),
            2,
        )
        self.assertFalse(
            self.lock.acquired
        )
        self.assertEqual(
            self.sleep_calls,
            [0.01],
        )

    def test_dependency_order_runs_across_cycles(
        self,
    ) -> None:
        self.roadmap_store.create(
            title="Foundation",
            goal="Build foundation",
            priority=100,
            task_id="foundation",
        )

        self.roadmap_store.create(
            title="Dependent",
            goal="Build dependent",
            priority=1,
            depends_on=("foundation",),
            task_id="dependent",
        )

        results = self.service.run_forever(
            max_cycles=2,
        )

        self.assertEqual(
            results[0].roadmap_task.task_id,
            "foundation",
        )
        self.assertEqual(
            results[1].roadmap_task.task_id,
            "dependent",
        )
        self.assertEqual(
            results[0].status,
            RuntimeCycleStatus.COMPLETED,
        )
        self.assertEqual(
            results[1].status,
            RuntimeCycleStatus.COMPLETED,
        )

    def test_multiple_running_tasks_fail_safely(
        self,
    ) -> None:
        first = self.roadmap_store.create(
            title="First",
            goal="First",
            task_id="first",
        )
        second = self.roadmap_store.create(
            title="Second",
            goal="Second",
            task_id="second",
        )

        self.roadmap_store.update_status(
            first.task_id,
            RoadmapTaskStatus.RUNNING,
        )
        self.roadmap_store.update_status(
            second.task_id,
            RoadmapTaskStatus.RUNNING,
        )

        with self.assertRaises(
            RuntimeError
        ):
            self.service.run_once()


if __name__ == "__main__":
    unittest.main()
