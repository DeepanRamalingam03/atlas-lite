from __future__ import annotations

import shutil
from pathlib import Path

from clients.base_client import BaseClient
from core.execution.plan_runner import PlanRunner
from core.execution.task_executor import (
    WorkerTaskExecutor,
)
from core.planning.execution_coordinator import (
    ExecutionCoordinator,
    PlanLifecycleStatus,
)
from core.planning.plan_state_store import (
    PlanStateStore,
)
from core.planning.task_result_store import (
    TaskResultStore,
)


class SuccessfulWorker(BaseClient):
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)

        return (
            f"Completed worker task number {self.calls}."
        )


class SecondTaskFailWorker(BaseClient):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1

        if self.calls == 1:
            return "First task completed."

        return ""


test_root = Path(".atlas_plan_runner_test")

if test_root.exists():
    shutil.rmtree(test_root)

plan_store = PlanStateStore(
    storage_path=test_root / "plans.json",
)

result_store = TaskResultStore(
    storage_path=test_root / "results.json",
)

coordinator = ExecutionCoordinator(
    state_store=plan_store,
)

successful_worker = SuccessfulWorker()

executor = WorkerTaskExecutor(
    worker=successful_worker,
    result_store=result_store,
    max_retries=1,
)

runner = PlanRunner(
    coordinator=coordinator,
    task_executor=executor,
    result_store=result_store,
)

plan_id, plan = coordinator.create_plan(
    goal="Create project status exporter",
    plan_id="success-plan",
)

steps = runner.run_until_pause(
    plan_id=plan_id,
    project_context="Atlas project context",
    max_steps=20,
)

assert len(plan.tasks) == 7
assert len(steps) == 7

final_progress = coordinator.progress(
    plan_id
)

assert final_progress.status == (
    PlanLifecycleStatus.COMPLETED
)
assert final_progress.completed_tasks == 7
assert final_progress.failed_tasks == 0

stored_results = result_store.list_for_plan(
    plan_id
)

assert len(stored_results) == 7
assert all(
    result.success
    for result in stored_results
)

assert successful_worker.calls == 7

assert "No dependency task results." in (
    successful_worker.prompts[0]
)

assert "Task 1" in successful_worker.prompts[1]
assert "Completed worker task number 1" in (
    successful_worker.prompts[1]
)

failure_plan_store = PlanStateStore(
    storage_path=test_root / "failure_plans.json",
)

failure_result_store = TaskResultStore(
    storage_path=test_root / "failure_results.json",
)

failure_coordinator = ExecutionCoordinator(
    state_store=failure_plan_store,
)

failure_worker = SecondTaskFailWorker()

failure_executor = WorkerTaskExecutor(
    worker=failure_worker,
    result_store=failure_result_store,
    max_retries=1,
)

failure_runner = PlanRunner(
    coordinator=failure_coordinator,
    task_executor=failure_executor,
    result_store=failure_result_store,
)

failure_plan_id, _ = (
    failure_coordinator.create_plan(
        goal="Create project status exporter",
        plan_id="failure-plan",
    )
)

failure_steps = failure_runner.run_until_pause(
    plan_id=failure_plan_id,
    project_context="Atlas project context",
    max_steps=20,
)

assert len(failure_steps) == 2

failure_progress = failure_coordinator.progress(
    failure_plan_id
)

assert failure_progress.status == (
    PlanLifecycleStatus.FAILED
)
assert failure_progress.completed_tasks == 1
assert failure_progress.failed_tasks == 1
assert failure_progress.blocked_tasks > 0

failed_result = failure_result_store.load(
    failure_plan_id,
    2,
)

assert failed_result is not None
assert failed_result.success is False
assert failure_worker.calls == 3

shutil.rmtree(test_root)

print("Plan runner passed")
