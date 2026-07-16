from __future__ import annotations

import shutil
from pathlib import Path

from core.orchestration.models import (
    WorkflowStatus,
)
from core.orchestration.state_store import (
    WorkflowStateError,
    WorkflowStateStore,
)


test_root = Path(".atlas_workflow_state_test")
storage_path = test_root / "workflows.json"

if test_root.exists():
    shutil.rmtree(test_root)

store = WorkflowStateStore(
    storage_path=storage_path,
)

record = store.create(
    user_id=100,
    goal="Build project status exporter",
    workflow_id="workflow-test",
)

assert record.workflow_id == "workflow-test"
assert record.user_id == 100
assert record.status == WorkflowStatus.CREATED
assert record.plan_id is None
assert record.current_task_id is None
assert record.approval_fingerprint is None
assert record.error is None

planning = store.update(
    "workflow-test",
    status=WorkflowStatus.PLANNING,
    summary="Creating execution plan.",
)

assert planning.status == WorkflowStatus.PLANNING

executing = store.update(
    "workflow-test",
    status=WorkflowStatus.EXECUTING,
    plan_id="plan-test",
    current_task_id=1,
    summary="Executing task 1.",
)

assert executing.plan_id == "plan-test"
assert executing.current_task_id == 1

validating = store.update(
    "workflow-test",
    status=WorkflowStatus.VALIDATING,
    clear_current_task=True,
    summary="Validating staged changes.",
)

assert validating.current_task_id is None

reviewing = store.update(
    "workflow-test",
    status=WorkflowStatus.REVIEWING,
    summary="Reviewing changes.",
)

assert reviewing.status == WorkflowStatus.REVIEWING

waiting = store.update(
    "workflow-test",
    status=WorkflowStatus.WAITING_APPROVAL,
    approval_fingerprint="a" * 64,
    summary="Waiting for human approval.",
)

assert waiting.approval_fingerprint == "a" * 64

progress = store.progress("workflow-test")

assert progress.waiting_for_human is True
assert progress.finished is False
assert progress.status == (
    WorkflowStatus.WAITING_APPROVAL
)

approved = store.update(
    "workflow-test",
    status=WorkflowStatus.APPROVED,
    summary="Human approved changes.",
)

assert approved.status == WorkflowStatus.APPROVED

applying = store.update(
    "workflow-test",
    status=WorkflowStatus.APPLYING,
    summary="Applying approved changes.",
)

assert applying.status == WorkflowStatus.APPLYING

completed = store.update(
    "workflow-test",
    status=WorkflowStatus.COMPLETED,
    summary="Workflow completed.",
    clear_approval=True,
    clear_error=True,
)

assert completed.status == WorkflowStatus.COMPLETED
assert completed.approval_fingerprint is None

completed_progress = store.progress(
    "workflow-test"
)

assert completed_progress.finished is True

reloaded_store = WorkflowStateStore(
    storage_path=storage_path,
)

reloaded = reloaded_store.require(
    "workflow-test"
)

assert reloaded.status == WorkflowStatus.COMPLETED
assert reloaded.plan_id == "plan-test"

second = store.create(
    user_id=100,
    goal="Second workflow",
)

assert second.workflow_id.startswith(
    "workflow-"
)

user_workflows = store.list_for_user(100)

assert len(user_workflows) == 2

latest = store.latest_for_user(100)

assert latest is not None
assert latest.workflow_id == second.workflow_id

try:
    store.update(
        "workflow-test",
        status=WorkflowStatus.EXECUTING,
    )
except WorkflowStateError:
    pass
else:
    raise AssertionError(
        "Completed workflows must not restart."
    )

try:
    store.create(
        user_id=100,
        goal="Duplicate",
        workflow_id="workflow-test",
    )
except WorkflowStateError:
    pass
else:
    raise AssertionError(
        "Duplicate workflow IDs must fail."
    )

try:
    store.require("missing-workflow")
except KeyError:
    pass
else:
    raise AssertionError(
        "Missing workflows must raise KeyError."
    )

store.delete(second.workflow_id)

assert store.latest_for_user(100) is not None
assert len(store.list_for_user(100)) == 1

shutil.rmtree(test_root)

print("Workflow state store passed")
