from __future__ import annotations

import shutil
from pathlib import Path

from core.planning.task_result_store import (
    TaskResultStore,
)


test_root = Path(".atlas_task_result_test")
storage_path = test_root / "results.json"

if test_root.exists():
    shutil.rmtree(test_root)

store = TaskResultStore(
    storage_path=storage_path,
)

assert store.load("plan-1", 1) is None

first_result = store.save(
    plan_id="plan-1",
    task_id=1,
    success=True,
    output="Analysis completed.",
    validation_result="Passed",
)

assert first_result.success is True
assert first_result.task_id == 1
assert first_result.retry_count == 0

loaded_first = store.load("plan-1", 1)

assert loaded_first == first_result

failed_result = store.save(
    plan_id="plan-1",
    task_id=2,
    success=False,
    error="Worker timeout",
    validation_result="Not run",
    retry_count=1,
)

assert failed_result.success is False
assert failed_result.error == "Worker timeout"
assert failed_result.retry_count == 1

plan_results = store.list_for_plan("plan-1")

assert [
    result.task_id
    for result in plan_results
] == [1, 2]

updated_result = store.save(
    plan_id="plan-1",
    task_id=2,
    success=True,
    output="Retry succeeded.",
    validation_result="Passed",
    retry_count=2,
)

assert updated_result.success is True

reloaded_second = store.load("plan-1", 2)

assert reloaded_second is not None
assert reloaded_second.success is True
assert reloaded_second.retry_count == 2
assert reloaded_second.error is None

store.save(
    plan_id="plan-2",
    task_id=1,
    success=True,
    output="Other plan",
)

store.delete_plan("plan-1")

assert store.list_for_plan("plan-1") == []
assert len(store.list_for_plan("plan-2")) == 1

try:
    store.save(
        plan_id="",
        task_id=1,
        success=True,
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Empty plan IDs must be rejected."
    )

try:
    store.save(
        plan_id="plan-1",
        task_id=0,
        success=True,
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Invalid task IDs must be rejected."
    )

shutil.rmtree(test_root)

print("Task result store passed")
