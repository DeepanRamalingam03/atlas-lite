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
from core.orchestration.recovery_manager import (
    RecoveryAction,
    WorkflowRecoveryManager,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)


@dataclass(slots=True, frozen=True)
class FakeChange:
    path: str


class FakePipeline:
    def __init__(self) -> None:
        self.call_count = 0

    def execute(self, goal: str):
        self.call_count += 1

        return SimpleNamespace(
            approved=True,
            file_changes=[
                FakeChange(
                    path="core/recovered.py"
                )
            ],
            manager_review="DECISION: APPROVED",
            test_result=SimpleNamespace(
                combined_output="Tests passed"
            ),
        )


class FakeReleaseCoordinator:
    def __init__(self) -> None:
        self.call_count = 0

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan=None,
    ):
        self.call_count += 1

        return SimpleNamespace(
            success=True,
            error=None,
        )


class WorkflowRecoveryManagerTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_recovery_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.store = WorkflowStateStore(
            storage_path=(
                self.root / "workflows.json"
            )
        )

        self.pipeline = FakePipeline()
        self.release = FakeReleaseCoordinator()

        self.orchestrator = ContinuousOrchestrator(
            pipeline=self.pipeline,
            release_coordinator=self.release,
            workflow_store=self.store,
            autonomy_policy=AutonomyPolicy(
                development_branches={"main"}
            ),
            branch="main",
            push=True,
        )

        self.manager = WorkflowRecoveryManager(
            orchestrator=self.orchestrator,
            workflow_store=self.store,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_missing_workflow_assessment(
        self,
    ) -> None:
        assessment = self.manager.assess(
            "missing"
        )

        self.assertEqual(
            assessment.action,
            RecoveryAction.NO_WORKFLOW,
        )
        self.assertFalse(
            assessment.recoverable
        )

    def test_pipeline_workflow_is_recoverable(
        self,
    ) -> None:
        self.store.create(
            user_id=100,
            goal="Recover pipeline",
            workflow_id="pipeline-recovery",
        )

        self.store.update(
            "pipeline-recovery",
            status=WorkflowStatus.PLANNING,
        )

        self.store.update(
            "pipeline-recovery",
            status=WorkflowStatus.EXECUTING,
        )

        assessment = self.manager.assess(
            "pipeline-recovery"
        )

        self.assertEqual(
            assessment.action,
            RecoveryAction.RESUME_PIPELINE,
        )
        self.assertTrue(
            assessment.recoverable
        )

        result = self.manager.recover(
            "pipeline-recovery"
        )

        self.assertTrue(
            result.completed
        )
        self.assertTrue(
            result.resumed
        )
        self.assertEqual(
            result.workflow.status,
            WorkflowStatus.COMPLETED,
        )
        self.assertEqual(
            self.pipeline.call_count,
            1,
        )
        self.assertEqual(
            self.release.call_count,
            1,
        )

    def test_release_stage_resumes_without_pipeline(
        self,
    ) -> None:
        self.store.create(
            user_id=100,
            goal="Recover release",
            workflow_id="release-recovery",
        )

        self.store.update(
            "release-recovery",
            status=WorkflowStatus.PLANNING,
        )
        self.store.update(
            "release-recovery",
            status=WorkflowStatus.EXECUTING,
        )
        self.store.update(
            "release-recovery",
            status=WorkflowStatus.VALIDATING,
        )
        self.store.update(
            "release-recovery",
            status=WorkflowStatus.REVIEWING,
        )
        self.store.update(
            "release-recovery",
            status=WorkflowStatus.WAITING_APPROVAL,
            approval_fingerprint="test-fingerprint",
        )
        self.store.update(
            "release-recovery",
            status=WorkflowStatus.APPROVED,
        )

        assessment = self.manager.assess(
            "release-recovery"
        )

        self.assertEqual(
            assessment.action,
            RecoveryAction.RESUME_RELEASE,
        )

        result = self.manager.recover(
            "release-recovery"
        )

        self.assertTrue(
            result.completed
        )
        self.assertTrue(
            result.resumed
        )
        self.assertEqual(
            self.pipeline.call_count,
            0,
        )
        self.assertEqual(
            self.release.call_count,
            1,
        )

    def test_waiting_approval_does_not_continue(
        self,
    ) -> None:
        self.store.create(
            user_id=100,
            goal="Blocked recovery",
            workflow_id="waiting-recovery",
        )

        self.store.update(
            "waiting-recovery",
            status=WorkflowStatus.PLANNING,
        )
        self.store.update(
            "waiting-recovery",
            status=WorkflowStatus.EXECUTING,
        )
        self.store.update(
            "waiting-recovery",
            status=WorkflowStatus.VALIDATING,
        )
        self.store.update(
            "waiting-recovery",
            status=WorkflowStatus.REVIEWING,
        )
        self.store.update(
            "waiting-recovery",
            status=WorkflowStatus.WAITING_APPROVAL,
            approval_fingerprint="blocked",
        )

        assessment = self.manager.assess(
            "waiting-recovery"
        )

        self.assertEqual(
            assessment.action,
            RecoveryAction.WAITING_FOR_HUMAN,
        )

        result = self.manager.recover(
            "waiting-recovery"
        )

        self.assertFalse(
            result.completed
        )
        self.assertTrue(
            result.waiting_for_human
        )
        self.assertTrue(
            result.resumed
        )
        self.assertEqual(
            self.pipeline.call_count,
            0,
        )
        self.assertEqual(
            self.release.call_count,
            0,
        )

    def test_completed_workflow_is_not_reexecuted(
        self,
    ) -> None:
        initial = self.orchestrator.run_goal(
            user_id=100,
            goal="Already completed",
            workflow_id="completed-recovery",
        )

        self.assertTrue(
            initial.completed
        )

        pipeline_calls = self.pipeline.call_count
        release_calls = self.release.call_count

        result = self.manager.recover(
            "completed-recovery"
        )

        self.assertTrue(
            result.completed
        )
        self.assertTrue(
            result.resumed
        )
        self.assertEqual(
            self.pipeline.call_count,
            pipeline_calls,
        )
        self.assertEqual(
            self.release.call_count,
            release_calls,
        )

    def test_latest_user_workflow_recovery(
        self,
    ) -> None:
        self.store.create(
            user_id=200,
            goal="Older workflow",
            workflow_id="older-workflow",
        )

        self.store.create(
            user_id=200,
            goal="Latest workflow",
            workflow_id="latest-workflow",
        )

        assessment = (
            self.manager.assess_latest_for_user(
                200
            )
        )

        self.assertIsNotNone(
            assessment.workflow
        )
        self.assertEqual(
            assessment.workflow.workflow_id,
            "latest-workflow",
        )

        result = (
            self.manager.recover_latest_for_user(
                200
            )
        )

        self.assertTrue(
            result.completed
        )
        self.assertEqual(
            result.workflow.workflow_id,
            "latest-workflow",
        )


if __name__ == "__main__":
    unittest.main()
