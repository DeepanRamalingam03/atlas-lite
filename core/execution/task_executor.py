from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from clients.base_client import BaseClient
from core.planning.models import PlanTask
from core.planning.task_result_store import (
    TaskExecutionResult,
    TaskResultStore,
)


TaskOutputValidator = Callable[[str], tuple[bool, str]]


@dataclass(slots=True, frozen=True)
class WorkerExecutionOutcome:
    result: TaskExecutionResult
    attempts: int


class WorkerTaskExecutor:
    """
    Executes one planned task using an AI worker.

    Responsibilities:
    - Build a precise worker prompt.
    - Execute the task through the configured worker client.
    - Validate the worker output.
    - Retry failed or invalid responses.
    - Persist the final task result.
    """

    def __init__(
        self,
        worker: BaseClient,
        result_store: TaskResultStore | None = None,
        validator: TaskOutputValidator | None = None,
        max_retries: int = 2,
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                "max_retries cannot be negative."
            )

        self.worker = worker
        self.result_store = (
            result_store or TaskResultStore()
        )
        self.validator = (
            validator or self._default_validator
        )
        self.max_retries = max_retries

    def execute(
        self,
        plan_id: str,
        task: PlanTask,
        project_context: str,
        previous_results: str = "",
    ) -> WorkerExecutionOutcome:
        cleaned_plan_id = plan_id.strip()
        cleaned_context = project_context.strip()

        if not cleaned_plan_id:
            raise ValueError(
                "plan_id cannot be empty."
            )

        if task.task_id < 1:
            raise ValueError(
                "task_id must be positive."
            )

        if not task.title.strip():
            raise ValueError(
                "Task title cannot be empty."
            )

        total_attempts = self.max_retries + 1
        last_output = ""
        last_error = ""
        last_validation = ""

        for attempt in range(1, total_attempts + 1):
            prompt = self._build_prompt(
                plan_id=cleaned_plan_id,
                task=task,
                project_context=cleaned_context,
                previous_results=previous_results,
                previous_output=last_output,
                previous_error=last_error,
                attempt=attempt,
                total_attempts=total_attempts,
            )

            try:
                output = self.worker.generate(
                    prompt
                ).strip()
            except Exception as exc:
                last_error = (
                    f"Worker execution error: "
                    f"{type(exc).__name__}: {exc}"
                )
                last_output = ""
                last_validation = "Worker call failed."
                continue

            if not output:
                last_error = (
                    "Worker returned an empty response."
                )
                last_output = ""
                last_validation = (
                    "Empty responses are invalid."
                )
                continue

            last_output = output

            try:
                valid, validation_message = (
                    self.validator(output)
                )
            except Exception as exc:
                last_error = (
                    "Task output validator failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                last_validation = last_error
                continue

            last_validation = (
                validation_message.strip()
                or (
                    "Validation passed."
                    if valid
                    else "Validation failed."
                )
            )

            if valid:
                saved_result = self.result_store.save(
                    plan_id=cleaned_plan_id,
                    task_id=task.task_id,
                    success=True,
                    output=output,
                    error=None,
                    validation_result=last_validation,
                    retry_count=attempt - 1,
                )

                return WorkerExecutionOutcome(
                    result=saved_result,
                    attempts=attempt,
                )

            last_error = last_validation

        failed_result = self.result_store.save(
            plan_id=cleaned_plan_id,
            task_id=task.task_id,
            success=False,
            output=last_output,
            error=(
                last_error
                or "Worker task execution failed."
            ),
            validation_result=(
                last_validation
                or "Validation did not pass."
            ),
            retry_count=self.max_retries,
        )

        return WorkerExecutionOutcome(
            result=failed_result,
            attempts=total_attempts,
        )

    @staticmethod
    def _build_prompt(
        plan_id: str,
        task: PlanTask,
        project_context: str,
        previous_results: str,
        previous_output: str,
        previous_error: str,
        attempt: int,
        total_attempts: int,
    ) -> str:
        retry_section = ""

        if attempt > 1:
            retry_section = (
                "\nPREVIOUS ATTEMPT\n"
                "================\n"
                f"Previous output:\n"
                f"{previous_output or 'No usable output.'}\n\n"
                f"Failure reason:\n"
                f"{previous_error or 'Unknown failure.'}\n\n"
                "Correct every reported issue. Do not repeat "
                "the failed response.\n"
            )

        return (
            "ATLAS WORKER TASK\n"
            "=================\n"
            f"Plan ID: {plan_id}\n"
            f"Task ID: {task.task_id}\n"
            f"Attempt: {attempt}/{total_attempts}\n\n"
            "TASK TITLE\n"
            "==========\n"
            f"{task.title}\n\n"
            "TASK DESCRIPTION\n"
            "================\n"
            f"{task.description}\n\n"
            "DEPENDENCIES\n"
            "============\n"
            f"{task.depends_on or 'None'}\n\n"
            "PROJECT CONTEXT\n"
            "===============\n"
            f"{project_context or 'No project context supplied.'}\n\n"
            "PREVIOUS TASK RESULTS\n"
            "=====================\n"
            f"{previous_results or 'No previous task results.'}\n"
            f"{retry_section}\n"
            "EXECUTION RULES\n"
            "===============\n"
            "- Complete only the assigned task.\n"
            "- Follow the supplied project context.\n"
            "- Do not invent files or APIs without stating assumptions.\n"
            "- Return complete and actionable output.\n"
            "- Do not claim commands were executed unless a tool "
            "actually executed them.\n"
        )

    @staticmethod
    def _default_validator(
        output: str,
    ) -> tuple[bool, str]:
        cleaned_output = output.strip()

        if not cleaned_output:
            return False, "Worker output is empty."

        return True, "Worker output is non-empty."
