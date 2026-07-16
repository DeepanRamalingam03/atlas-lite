from __future__ import annotations

import shutil
from pathlib import Path

from core.planning.models import (
    ExecutionPlan,
    PlanTask,
    TaskStatus,
)
from core.planning.plan_state_store import (
    PlanStateStore,
)


test_root = Path(".atlas_plan_state_test")
storage_path = test_root / "plans.json"

if test_root.exists():
    shutil.rmtree(test_root)

store = PlanStateStore(
    storage_path=storage_path,
)

plan = ExecutionPlan(
    goal="Build authentication"
)

plan.add_task(
    PlanTask(
        task_id=1,
        title="Analyze",
        description="Analyze current system",
        status=TaskStatus.COMPLETED,
    )
)

plan.add_task(
    PlanTask(
        task_id=2,
        title="Implement",
        description="Implement authentication",
        status=TaskStatus.RUNNING,
        depends_on=[1],
    )
)

plan.add_task(
    PlanTask(
        task_id=3,
        title="Test",
        description="Run tests",
        status=TaskStatus.PENDING,
        depends_on=[2],
    )
)

store.save(
    plan_id="auth-plan",
    plan=plan,
)

assert store.exists("auth-plan") is True
assert store.list_plan_ids() == ["auth-plan"]

loaded_plan = store.load("auth-plan")

assert loaded_plan is not None
assert loaded_plan.goal == "Build authentication"
assert len(loaded_plan.tasks) == 3

assert loaded_plan.tasks[0].status == (
    TaskStatus.COMPLETED
)
assert loaded_plan.tasks[1].status == (
    TaskStatus.RUNNING
)
assert loaded_plan.tasks[2].status == (
    TaskStatus.PENDING
)

assert loaded_plan.tasks[1].depends_on == [1]
assert loaded_plan.tasks[2].depends_on == [2]

loaded_plan.tasks[1].status = (
    TaskStatus.COMPLETED
)
loaded_plan.tasks[2].status = (
    TaskStatus.RUNNING
)

store.save(
    plan_id="auth-plan",
    plan=loaded_plan,
)

reloaded_plan = store.load("auth-plan")

assert reloaded_plan is not None
assert reloaded_plan.tasks[1].status == (
    TaskStatus.COMPLETED
)
assert reloaded_plan.tasks[2].status == (
    TaskStatus.RUNNING
)

second_plan = ExecutionPlan(
    goal="Build reporting"
)

second_plan.add_task(
    PlanTask(
        task_id=1,
        title="Report task",
        description="Create report",
    )
)

store.save(
    plan_id="report-plan",
    plan=second_plan,
)

assert store.list_plan_ids() == [
    "auth-plan",
    "report-plan",
]

store.delete("auth-plan")

assert store.load("auth-plan") is None
assert store.exists("auth-plan") is False
assert store.list_plan_ids() == [
    "report-plan",
]

try:
    store.save("", plan)
except ValueError:
    pass
else:
    raise AssertionError(
        "Empty plan IDs must be rejected."
    )

shutil.rmtree(test_root)

print("Plan state store passed")
