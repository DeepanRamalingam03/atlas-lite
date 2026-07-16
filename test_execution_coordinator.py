from __future__ import annotations

import shutil
from pathlib import Path

from core.planning.execution_coordinator import (
    ExecutionCoordinator,
    PlanLifecycleStatus,
)
from core.planning.models import TaskStatus
from core.planning.plan_state_store import (
    PlanStateStore,
)
from core.planning.task_scheduler import (
    TaskSchedulingError,
)


test_root = Path(
    ".atlas_execution_coordinator_test"
)
storage_path = test_root / "plans.json"

if test_root.exists():
    shutil.rmtree(test_root)

store = PlanStateStore(
    storage_path=storage_path,
)

coordinator = ExecutionCoordinator(
    state_store=store,
)

plan_id, plan = coordinator.create_plan(
    goal="Add JWT authentication",
    plan_id="jwt-plan",
)

assert plan_id == "jwt-plan"
assert plan.goal == "Add JWT authentication"
assert len(plan.tasks) == 8

assert coordinator.list_plan_ids() == [
    "jwt-plan"
]

initial_progress = coordinator.progress(
    "jwt-plan"
)

assert initial_progress.status == (
    PlanLifecycleStatus.PENDING
)
assert initial_progress.total_tasks == 8
assert initial_progress.pending_tasks == 8
assert initial_progress.running_tasks == 0
assert initial_progress.completed_tasks == 0
assert initial_progress.failed_tasks == 0
assert initial_progress.blocked_tasks == 0
assert initial_progress.next_task_id == 1

first_task = coordinator.start_next_task(
    "jwt-plan"
)

assert first_task is not None
assert first_task.task_id == 1
assert first_task.status == TaskStatus.RUNNING

running_progress = coordinator.progress(
    "jwt-plan"
)

assert running_progress.status == (
    PlanLifecycleStatus.RUNNING
)
assert running_progress.running_tasks == 1
assert running_progress.pending_tasks == 7
assert running_progress.next_task_id is None

try:
    coordinator.start_next_task("jwt-plan")
except TaskSchedulingError:
    pass
else:
    raise AssertionError(
        "A second task must not start while "
        "another task is running."
    )

coordinator.complete_task(
    plan_id="jwt-plan",
    task_id=1,
)

after_first_completion = coordinator.progress(
    "jwt-plan"
)

assert after_first_completion.status == (
    PlanLifecycleStatus.PENDING
)
assert after_first_completion.completed_tasks == 1
assert after_first_completion.next_task_id == 2

second_task = coordinator.start_next_task(
    "jwt-plan"
)

assert second_task is not None
assert second_task.task_id == 2

coordinator.fail_task(
    plan_id="jwt-plan",
    task_id=2,
)

failed_progress = coordinator.progress(
    "jwt-plan"
)

assert failed_progress.status == (
    PlanLifecycleStatus.FAILED
)
assert failed_progress.failed_tasks == 1
assert failed_progress.blocked_tasks > 0
assert failed_progress.next_task_id is None

retried_task = coordinator.retry_failed_task(
    plan_id="jwt-plan",
    task_id=2,
)

assert retried_task.status == TaskStatus.PENDING

retry_progress = coordinator.progress(
    "jwt-plan"
)

assert retry_progress.status == (
    PlanLifecycleStatus.PENDING
)
assert retry_progress.failed_tasks == 0
assert retry_progress.next_task_id == 2

reloaded_coordinator = ExecutionCoordinator(
    state_store=PlanStateStore(
        storage_path=storage_path,
    ),
)

reloaded_plan = reloaded_coordinator.load_plan(
    "jwt-plan"
)

assert reloaded_plan.goal == (
    "Add JWT authentication"
)
assert reloaded_plan.tasks[0].status == (
    TaskStatus.COMPLETED
)
assert reloaded_plan.tasks[1].status == (
    TaskStatus.PENDING
)

generated_plan_id, _ = (
    reloaded_coordinator.create_plan(
        goal="Build reporting",
    )
)

assert generated_plan_id.startswith("plan-")
assert len(generated_plan_id) == 17

try:
    coordinator.create_plan(
        goal="Duplicate",
        plan_id="jwt-plan",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Duplicate plan IDs must be rejected."
    )

try:
    coordinator.load_plan("missing-plan")
except KeyError:
    pass
else:
    raise AssertionError(
        "Missing plans must raise KeyError."
    )

coordinator.delete_plan("jwt-plan")

assert "jwt-plan" not in (
    coordinator.list_plan_ids()
)

shutil.rmtree(test_root)

print("Execution coordinator passed")
