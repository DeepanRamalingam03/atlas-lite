from __future__ import annotations

import shutil
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from core.orchestration.autonomy_policy import (
    AutonomyPolicy,
)
from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
)
from core.orchestration.models import (
    WorkflowStatus,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)


@dataclass(slots=True, frozen=True)
class FakeFileChange:
    path: str
    content: str = ""


class FakePipeline:
    def __init__(
        self,
        *,
        approved: bool = True,
        paths: tuple[str, ...] = (
            "core/example.py",
            "test_example.py",
        ),
    ) -> None:
        self.approved = approved
        self.paths = paths
        self.goals: list[str] = []

    def execute(self, goal: str):
        self.goals.append(goal)

        return SimpleNamespace(
            approved=self.approved,
            file_changes=[
                FakeFileChange(path=path)
                for path in self.paths
            ],
            manager_review=(
                "DECISION: APPROVED"
                if self.approved
                else (
                    "DECISION: REJECTED\n\n"
                    "REASON:\nImplementation incomplete."
                )
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
        error: str | None = None,
    ) -> None:
        self.success = success
        self.error = error
        self.calls: list[dict[str, object]] = []

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan=None,
    ):
        self.calls.append(
            {
                "commit_message": commit_message,
                "push": push,
                "remote": remote,
                "branch": branch,
            }
        )

        return SimpleNamespace(
            success=self.success,
            error=self.error,
        )


class ContinuousOrchestratorTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.test_root = Path(
            ".atlas_continuous_loop_test"
        )

        if self.test_root.exists():
            shutil.rmtree(
                self.test_root
            )

        self.test_root.mkdir(
            parents=True
        )

        self.workflow_store = WorkflowStateStore(
            storage_path=(
                self.test_root
                / "workflows.json"
            )
        )

    def tearDown(self) -> None:
        if self.test_root.exists():
            shutil.rmtree(
                self.test_root
            )

    def test_routine_change_completes(
        self,
    ) -> None:
        pipeline = FakePipeline()
        release = FakeReleaseCoordinator()

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release,
            workflow_store=self.workflow_store,
            autonomy_policy=AutonomyPolicy(
                development_branches={
                    "main",
                }
            ),
            branch="main",
            push=True,
        )

        result = orchestrator.run_goal(
            user_id=100,
            goal="Build a tested example module",
            workflow_id="workflow-success",
            commit_message=(
                "Phase 17 - Test continuous loop"
            ),
        )

        self.assertTrue(
            result.completed
        )
        self.assertFalse(
            result.waiting_for_human
        )
        self.assertIsNone(
            result.error
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.COMPLETED,
        )
        self.assertEqual(
            len(release.calls),
            1,
        )
        self.assertEqual(
            release.calls[0]["branch"],
            "main",
        )
        self.assertTrue(
            release.calls[0]["push"]
        )

        persisted = (
            self.workflow_store.require(
                "workflow-success"
            )
        )

        self.assertEqual(
            persisted.status,
            WorkflowStatus.COMPLETED,
        )
        self.assertIsNone(
            persisted.approval_fingerprint
        )

    def test_constitution_change_waits_for_human(
        self,
    ) -> None:
        pipeline = FakePipeline(
            paths=(
                "atlas_core/constitution/HANDOFF.md",
            )
        )
        release = FakeReleaseCoordinator()

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release,
            workflow_store=self.workflow_store,
            branch="main",
            push=True,
        )

        result = orchestrator.run_goal(
            user_id=100,
            goal="Change the Constitution",
            workflow_id="workflow-blocked",
        )

        self.assertFalse(
            result.completed
        )
        self.assertTrue(
            result.waiting_for_human
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.WAITING_APPROVAL,
        )
        self.assertEqual(
            len(release.calls),
            0,
        )
        self.assertIsNotNone(
            result.autonomy_decision
        )
        self.assertTrue(
            result.autonomy_decision.blocked
        )

    def test_rejected_pipeline_fails_workflow(
        self,
    ) -> None:
        pipeline = FakePipeline(
            approved=False
        )
        release = FakeReleaseCoordinator()

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release,
            workflow_store=self.workflow_store,
        )

        result = orchestrator.run_goal(
            user_id=100,
            goal="Build rejected feature",
            workflow_id="workflow-rejected",
        )

        self.assertFalse(
            result.completed
        )
        self.assertFalse(
            result.waiting_for_human
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.FAILED,
        )
        self.assertIn(
            "REJECTED",
            result.error or "",
        )
        self.assertEqual(
            len(release.calls),
            0,
        )

    def test_release_failure_is_persisted(
        self,
    ) -> None:
        pipeline = FakePipeline()
        release = FakeReleaseCoordinator(
            success=False,
            error="Git push failed",
        )

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release,
            workflow_store=self.workflow_store,
        )

        result = orchestrator.run_goal(
            user_id=100,
            goal="Build release failure example",
            workflow_id="workflow-release-failure",
        )

        self.assertFalse(
            result.completed
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.FAILED,
        )
        self.assertEqual(
            result.error,
            "Git push failed",
        )
        self.assertEqual(
            len(release.calls),
            1,
        )

    def test_unsafe_pipeline_path_fails(
        self,
    ) -> None:
        pipeline = FakePipeline(
            paths=(
                "../outside.py",
            )
        )
        release = FakeReleaseCoordinator()

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release,
            workflow_store=self.workflow_store,
        )

        result = orchestrator.run_goal(
            user_id=100,
            goal="Write unsafe file",
            workflow_id="workflow-unsafe",
        )

        self.assertFalse(
            result.completed
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.FAILED,
        )
        self.assertIn(
            "unsafe file path",
            result.error or "",
        )
        self.assertEqual(
            len(release.calls),
            0,
        )

    def test_disallowed_push_branch_waits_for_human(
        self,
    ) -> None:
        pipeline = FakePipeline()
        release = FakeReleaseCoordinator()

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release,
            workflow_store=self.workflow_store,
            autonomy_policy=AutonomyPolicy(
                development_branches={
                    "main",
                }
            ),
            branch="production",
            push=True,
        )

        result = orchestrator.run_goal(
            user_id=100,
            goal="Build production branch example",
            workflow_id="workflow-production",
        )

        self.assertFalse(
            result.completed
        )
        self.assertTrue(
            result.waiting_for_human
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.WAITING_APPROVAL,
        )
        self.assertEqual(
            len(release.calls),
            0,
        )


if __name__ == "__main__":
    unittest.main()
