from __future__ import annotations

import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from core.orchestration.retry_policy import (
    FailureClass,
    FailureClassifier,
    RetryStateStore,
    RuntimeRetryPolicy,
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


class SequencedPipeline:
    def __init__(
        self,
        outcomes: list[str],
    ) -> None:
        self.outcomes = list(outcomes)
        self.call_count = 0

    def execute(self, goal: str):
        self.call_count += 1

        outcome = self.outcomes.pop(0)

        if outcome == "timeout":
            raise TimeoutError(
                "Provider request timed out"
            )

        if outcome == "human":
            raise RuntimeError(
                "MFA authentication required"
            )

        if outcome == "rejected":
            return SimpleNamespace(
                approved=False,
                file_changes=[],
                manager_review=(
                    "DECISION: REJECTED"
                ),
                test_result=SimpleNamespace(
                    combined_output=(
                        "Validation failed"
                    )
                ),
            )

        return SimpleNamespace(
            approved=True,
            file_changes=[
                SimpleNamespace(
                    path="core/retry_success.py"
                )
            ],
            manager_review=(
                "DECISION: APPROVED"
            ),
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


class RuntimeRetryPolicyTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_retry_policy_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_failure_classification(
        self,
    ) -> None:
        classifier = FailureClassifier()

        self.assertEqual(
            classifier.classify(
                "Connection timed out"
            ).failure_class,
            FailureClass.TRANSIENT,
        )

        self.assertEqual(
            classifier.classify(
                "MFA authentication required"
            ).failure_class,
            FailureClass.HUMAN_BLOCKER,
        )

        self.assertEqual(
            classifier.classify(
                "DECISION: REJECTED"
            ).failure_class,
            FailureClass.PERMANENT,
        )

    def test_exponential_backoff_persists(
        self,
    ) -> None:
        store = RetryStateStore(
            self.root / "retries.json"
        )

        policy = RuntimeRetryPolicy(
            state_store=store,
            max_attempts=4,
            initial_delay_seconds=10,
            multiplier=2,
            max_delay_seconds=100,
        )

        now = datetime(
            2026,
            7,
            17,
            tzinfo=timezone.utc,
        )

        first = policy.register_failure(
            "task",
            "Connection timed out",
            now=now,
        )

        second = policy.register_failure(
            "task",
            "Connection timed out",
            now=now,
        )

        third = policy.register_failure(
            "task",
            "Connection timed out",
            now=now,
        )

        self.assertEqual(
            first.delay_seconds,
            10,
        )
        self.assertEqual(
            second.delay_seconds,
            20,
        )
        self.assertEqual(
            third.delay_seconds,
            40,
        )

        persisted = store.require("task")

        self.assertEqual(
            persisted.attempt_count,
            3,
        )
        self.assertFalse(
            persisted.exhausted
        )

    def test_retry_limit_exhaustion(
        self,
    ) -> None:
        policy = RuntimeRetryPolicy(
            state_store=RetryStateStore(
                self.root / "limit.json"
            ),
            max_attempts=2,
            initial_delay_seconds=0,
        )

        first = policy.register_failure(
            "task",
            "Service unavailable",
        )

        second = policy.register_failure(
            "task",
            "Service unavailable",
        )

        self.assertTrue(first.retry)
        self.assertFalse(second.retry)
        self.assertTrue(second.exhausted)

    def test_readiness_uses_timestamp(
        self,
    ) -> None:
        policy = RuntimeRetryPolicy(
            state_store=RetryStateStore(
                self.root / "ready.json"
            ),
            max_attempts=3,
            initial_delay_seconds=30,
        )

        now = datetime.now(timezone.utc)

        policy.register_failure(
            "task",
            "Connection timed out",
            now=now,
        )

        self.assertFalse(
            policy.is_ready(
                "task",
                now=now + timedelta(seconds=10),
            )
        )

        self.assertTrue(
            policy.is_ready(
                "task",
                now=now + timedelta(seconds=31),
            )
        )

    def test_transient_failure_retries_and_completes(
        self,
    ) -> None:
        pipeline = SequencedPipeline(
            ["timeout", "success"]
        )

        roadmap_store = RoadmapTaskStore(
            self.root / "roadmap.json"
        )

        workflow_store = WorkflowStateStore(
            self.root / "workflows.json"
        )

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
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

        service = ContinuousRuntimeService(
            roadmap_store=roadmap_store,
            roadmap_selector=RoadmapTaskSelector(
                roadmap_store
            ),
            orchestrator=orchestrator,
            recovery_manager=(
                WorkflowRecoveryManager(
                    orchestrator=orchestrator,
                    workflow_store=workflow_store,
                )
            ),
            process_lock=RuntimeProcessLock(
                self.root / "runtime.lock"
            ),
            retry_policy=RuntimeRetryPolicy(
                state_store=RetryStateStore(
                    self.root / "runtime_retry.json"
                ),
                max_attempts=3,
                initial_delay_seconds=0,
            ),
            user_id=100,
            idle_seconds=0,
        )

        roadmap_store.create(
            title="Retry task",
            goal="Retry transient task",
            task_id="retry-task",
        )

        first = service.run_once()

        self.assertEqual(
            first.status,
            RuntimeCycleStatus.RETRY_SCHEDULED,
        )

        self.assertEqual(
            roadmap_store.require(
                "retry-task"
            ).status,
            RoadmapTaskStatus.RUNNING,
        )

        second = service.run_once()

        self.assertEqual(
            second.status,
            RuntimeCycleStatus.COMPLETED,
        )

        self.assertEqual(
            pipeline.call_count,
            2,
        )

        self.assertIsNone(
            service.retry_policy.state_store.load(
                "retry-task"
            )
        )

    def test_human_blocker_is_not_retried(
        self,
    ) -> None:
        pipeline = SequencedPipeline(
            ["human"]
        )

        roadmap_store = RoadmapTaskStore(
            self.root / "human_roadmap.json"
        )

        workflow_store = WorkflowStateStore(
            self.root / "human_workflows.json"
        )

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
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

        service = ContinuousRuntimeService(
            roadmap_store=roadmap_store,
            roadmap_selector=RoadmapTaskSelector(
                roadmap_store
            ),
            orchestrator=orchestrator,
            recovery_manager=(
                WorkflowRecoveryManager(
                    orchestrator=orchestrator,
                    workflow_store=workflow_store,
                )
            ),
            retry_policy=RuntimeRetryPolicy(
                state_store=RetryStateStore(
                    self.root / "human_retry.json"
                ),
                max_attempts=4,
                initial_delay_seconds=0,
            ),
            user_id=100,
            idle_seconds=0,
        )

        roadmap_store.create(
            title="Human task",
            goal="Requires MFA",
            task_id="human-task",
        )

        result = service.run_once()

        self.assertEqual(
            result.status,
            RuntimeCycleStatus.WAITING_FOR_HUMAN,
        )

        self.assertEqual(
            roadmap_store.require(
                "human-task"
            ).status,
            RoadmapTaskStatus.BLOCKED,
        )

        self.assertEqual(
            pipeline.call_count,
            1,
        )

    def test_permanent_failure_fails_immediately(
        self,
    ) -> None:
        policy = RuntimeRetryPolicy(
            state_store=RetryStateStore(
                self.root / "permanent.json"
            ),
            max_attempts=5,
            initial_delay_seconds=0,
        )

        decision = policy.register_failure(
            "task",
            "DECISION: REJECTED",
        )

        self.assertFalse(decision.retry)
        self.assertTrue(decision.exhausted)
        self.assertEqual(
            decision.classification.failure_class,
            FailureClass.PERMANENT,
        )


if __name__ == "__main__":
    unittest.main()
