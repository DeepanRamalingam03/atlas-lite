from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
    ContinuousRunResult,
)
from core.orchestration.models import (
    WorkflowRecord,
    WorkflowStatus,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)


class RecoveryAction(str, Enum):
    NO_WORKFLOW = "no_workflow"
    ALREADY_FINISHED = "already_finished"
    WAITING_FOR_HUMAN = "waiting_for_human"
    RESUME_PIPELINE = "resume_pipeline"
    RESUME_RELEASE = "resume_release"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True, frozen=True)
class RecoveryAssessment:
    action: RecoveryAction
    workflow: WorkflowRecord | None
    message: str

    @property
    def recoverable(self) -> bool:
        return self.action in {
            RecoveryAction.RESUME_PIPELINE,
            RecoveryAction.RESUME_RELEASE,
        }


class WorkflowRecoveryManager:
    """
    Recovers persisted workflows after process or server restarts.
    """

    PIPELINE_STATUSES = frozenset(
        {
            WorkflowStatus.CREATED,
            WorkflowStatus.PLANNING,
            WorkflowStatus.EXECUTING,
            WorkflowStatus.VALIDATING,
            WorkflowStatus.REVIEWING,
        }
    )

    RELEASE_STATUSES = frozenset(
        {
            WorkflowStatus.APPROVED,
            WorkflowStatus.APPLYING,
        }
    )

    FINISHED_STATUSES = frozenset(
        {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.STOPPED,
        }
    )

    def __init__(
        self,
        orchestrator: ContinuousOrchestrator,
        workflow_store: WorkflowStateStore | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.workflow_store = (
            workflow_store
            or orchestrator.workflow_store
        )

    def assess(
        self,
        workflow_id: str,
    ) -> RecoveryAssessment:
        workflow = self.workflow_store.load(
            workflow_id
        )

        if workflow is None:
            return RecoveryAssessment(
                action=RecoveryAction.NO_WORKFLOW,
                workflow=None,
                message=(
                    "Workflow does not exist and cannot be recovered."
                ),
            )

        if workflow.status in self.FINISHED_STATUSES:
            return RecoveryAssessment(
                action=RecoveryAction.ALREADY_FINISHED,
                workflow=workflow,
                message=(
                    "Workflow is already in a terminal state."
                ),
            )

        if (
            workflow.status
            == WorkflowStatus.WAITING_APPROVAL
        ):
            return RecoveryAssessment(
                action=RecoveryAction.WAITING_FOR_HUMAN,
                workflow=workflow,
                message=(
                    "Workflow is waiting for human intervention."
                ),
            )

        if workflow.status in self.PIPELINE_STATUSES:
            return RecoveryAssessment(
                action=RecoveryAction.RESUME_PIPELINE,
                workflow=workflow,
                message=(
                    "Workflow can restart from the development pipeline."
                ),
            )

        if workflow.status in self.RELEASE_STATUSES:
            return RecoveryAssessment(
                action=RecoveryAction.RESUME_RELEASE,
                workflow=workflow,
                message=(
                    "Workflow can continue from the release stage."
                ),
            )

        return RecoveryAssessment(
            action=RecoveryAction.UNSUPPORTED,
            workflow=workflow,
            message=(
                "Workflow status is not supported for recovery."
            ),
        )

    def recover(
        self,
        workflow_id: str,
        *,
        commit_message: str | None = None,
    ) -> ContinuousRunResult:
        assessment = self.assess(
            workflow_id
        )

        if assessment.workflow is None:
            raise KeyError(
                f"Workflow does not exist: {workflow_id}"
            )

        return self.orchestrator.resume_workflow(
            workflow_id,
            commit_message=commit_message,
        )

    def assess_latest_for_user(
        self,
        user_id: int,
    ) -> RecoveryAssessment:
        workflow = self.workflow_store.latest_for_user(
            user_id
        )

        if workflow is None:
            return RecoveryAssessment(
                action=RecoveryAction.NO_WORKFLOW,
                workflow=None,
                message=(
                    "No persisted workflow exists for this user."
                ),
            )

        return self.assess(
            workflow.workflow_id
        )

    def recover_latest_for_user(
        self,
        user_id: int,
        *,
        commit_message: str | None = None,
    ) -> ContinuousRunResult:
        assessment = self.assess_latest_for_user(
            user_id
        )

        if assessment.workflow is None:
            raise KeyError(
                f"No workflow exists for user: {user_id}"
            )

        return self.recover(
            assessment.workflow.workflow_id,
            commit_message=commit_message,
        )
