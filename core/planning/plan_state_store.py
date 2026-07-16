from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from core.planning.dependency_validator import (
    DependencyValidator,
)
from core.planning.models import (
    ExecutionPlan,
    PlanTask,
    TaskStatus,
)


class PlanStateStore:
    """
    Thread-safe JSON-backed storage for execution plans.

    Plans can be restored after:
    - process restart,
    - Discord bot restart,
    - server reboot,
    - human approval pause.
    """

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/execution_plans.json"
        ),
        dependency_validator: DependencyValidator | None = None,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.dependency_validator = (
            dependency_validator or DependencyValidator()
        )
        self._lock = Lock()

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self._write_data({})

    def save(
        self,
        plan_id: str,
        plan: ExecutionPlan,
    ) -> None:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError(
                "plan_id cannot be empty."
            )

        self.dependency_validator.validate(plan)

        payload = self._serialize_plan(plan)

        with self._lock:
            data = self._read_data()
            data[cleaned_plan_id] = payload
            self._write_data(data)

    def load(
        self,
        plan_id: str,
    ) -> ExecutionPlan | None:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError(
                "plan_id cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            payload = data.get(cleaned_plan_id)

        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Stored plan is invalid: {cleaned_plan_id}"
            )

        plan = self._deserialize_plan(payload)
        self.dependency_validator.validate(plan)

        return plan

    def delete(
        self,
        plan_id: str,
    ) -> None:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError(
                "plan_id cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            data.pop(cleaned_plan_id, None)
            self._write_data(data)

    def list_plan_ids(self) -> list[str]:
        with self._lock:
            data = self._read_data()

        return sorted(data.keys())

    def exists(
        self,
        plan_id: str,
    ) -> bool:
        return self.load(plan_id) is not None

    @staticmethod
    def _serialize_plan(
        plan: ExecutionPlan,
    ) -> dict[str, Any]:
        return {
            "goal": plan.goal,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "description": task.description,
                    "status": task.status.value,
                    "depends_on": list(task.depends_on),
                }
                for task in plan.tasks
            ],
        }

    @staticmethod
    def _deserialize_plan(
        payload: dict[str, Any],
    ) -> ExecutionPlan:
        goal = payload.get("goal")
        raw_tasks = payload.get("tasks")

        if not isinstance(goal, str):
            raise RuntimeError(
                "Stored plan goal is invalid."
            )

        if not isinstance(raw_tasks, list):
            raise RuntimeError(
                "Stored plan task list is invalid."
            )

        plan = ExecutionPlan(goal=goal)

        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                raise RuntimeError(
                    "Stored plan task is invalid."
                )

            try:
                task = PlanTask(
                    task_id=int(raw_task["task_id"]),
                    title=str(raw_task["title"]),
                    description=str(
                        raw_task["description"]
                    ),
                    status=TaskStatus(
                        raw_task["status"]
                    ),
                    depends_on=[
                        int(dependency)
                        for dependency in raw_task.get(
                            "depends_on",
                            [],
                        )
                    ],
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise RuntimeError(
                    "Stored plan task contains invalid data."
                ) from exc

            plan.add_task(task)

        return plan

    def _read_data(
        self,
    ) -> dict[str, dict[str, Any]]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return {}

            parsed = json.loads(content)

            if not isinstance(parsed, dict):
                raise RuntimeError(
                    "Execution plan store must contain "
                    "a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Execution plan store contains invalid JSON."
            ) from exc

    def _write_data(
        self,
        data: dict[str, dict[str, Any]],
    ) -> None:
        temporary_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix + ".tmp"
            )
        )

        temporary_path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.storage_path
        )
