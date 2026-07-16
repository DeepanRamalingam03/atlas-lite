from __future__ import annotations

import shutil
from pathlib import Path

from clients.base_client import BaseClient
from core.execution.task_executor import (
    WorkerTaskExecutor,
)
from core.planning.models import PlanTask
from core.planning.task_result_store import (
    TaskResultStore,
)


class SuccessfulWorker(BaseClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        return (
            "Implementation analysis completed successfully."
        )


class RetryWorker(BaseClient):
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)

        if self.calls == 1:
            return "INVALID"

        return "VALID implementation result"


class FailingWorker(BaseClient):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return ""


def strict_validator(
    output: str,
) -> tuple[bool, str]:
    if "VALID" in output and "INVALID" not in output:
        return True, "Strict validation passed."

    return False, "Expected VALID output."


test_root = Path(".atlas_worker_executor_test")

if test_root.exists():
    shutil.rmtree(test_root)

result_store = TaskResultStore(
    storage_path=test_root / "results.json",
)

task = PlanTask(
    task_id=1,
    title="Analyze implementation",
    description="Inspect the current project implementation.",
)

successful_worker = SuccessfulWorker()

successful_executor = WorkerTaskExecutor(
    worker=successful_worker,
    result_store=result_store,
    max_retries=2,
)

successful_outcome = successful_executor.execute(
    plan_id="plan-success",
    task=task,
    project_context="Atlas project context",
)

assert successful_outcome.result.success is True
assert successful_outcome.attempts == 1
assert successful_outcome.result.retry_count == 0
assert (
    "Implementation analysis completed"
    in successful_outcome.result.output
)
assert len(successful_worker.prompts) == 1
assert "ATLAS WORKER TASK" in successful_worker.prompts[0]
assert "Analyze implementation" in successful_worker.prompts[0]
assert "Atlas project context" in successful_worker.prompts[0]

retry_worker = RetryWorker()

retry_executor = WorkerTaskExecutor(
    worker=retry_worker,
    result_store=result_store,
    validator=strict_validator,
    max_retries=2,
)

retry_outcome = retry_executor.execute(
    plan_id="plan-retry",
    task=task,
    project_context="Project context",
    previous_results="Task zero completed.",
)

assert retry_outcome.result.success is True
assert retry_outcome.attempts == 2
assert retry_outcome.result.retry_count == 1
assert retry_worker.calls == 2
assert "PREVIOUS ATTEMPT" in retry_worker.prompts[1]
assert "Expected VALID output." in retry_worker.prompts[1]
assert "Task zero completed." in retry_worker.prompts[1]

failing_worker = FailingWorker()

failing_executor = WorkerTaskExecutor(
    worker=failing_worker,
    result_store=result_store,
    max_retries=2,
)

failed_outcome = failing_executor.execute(
    plan_id="plan-failed",
    task=task,
    project_context="Project context",
)

assert failed_outcome.result.success is False
assert failed_outcome.attempts == 3
assert failed_outcome.result.retry_count == 2
assert failed_outcome.result.error is not None
assert "empty response" in (
    failed_outcome.result.error.lower()
)
assert failing_worker.calls == 3

stored_success = result_store.load(
    "plan-success",
    1,
)

assert stored_success is not None
assert stored_success.success is True

stored_retry = result_store.load(
    "plan-retry",
    1,
)

assert stored_retry is not None
assert stored_retry.retry_count == 1

stored_failure = result_store.load(
    "plan-failed",
    1,
)

assert stored_failure is not None
assert stored_failure.success is False

shutil.rmtree(test_root)

print("Worker task executor passed")
