from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(slots=True, frozen=True)
class TaskExecutionResult:
    plan_id: str
    task_id: int
    success: bool
    output: str
    error: str | None
    validation_result: str | None
    retry_count: int
    created_at: str


class TaskResultStore:
    """
    Thread-safe JSON-backed storage for task execution results.
    """

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/task_results.json"
        ),
    ) -> None:
        self.storage_path = Path(storage_path)
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
        task_id: int,
        success: bool,
        output: str = "",
        error: str | None = None,
        validation_result: str | None = None,
        retry_count: int = 0,
    ) -> TaskExecutionResult:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError("plan_id cannot be empty.")

        if task_id < 1:
            raise ValueError("task_id must be positive.")

        if retry_count < 0:
            raise ValueError(
                "retry_count cannot be negative."
            )

        result = TaskExecutionResult(
            plan_id=cleaned_plan_id,
            task_id=task_id,
            success=success,
            output=output,
            error=error,
            validation_result=validation_result,
            retry_count=retry_count,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        key = self._key(
            plan_id=cleaned_plan_id,
            task_id=task_id,
        )

        with self._lock:
            data = self._read_data()
            data[key] = asdict(result)
            self._write_data(data)

        return result

    def load(
        self,
        plan_id: str,
        task_id: int,
    ) -> TaskExecutionResult | None:
        key = self._key(
            plan_id=plan_id,
            task_id=task_id,
        )

        with self._lock:
            data = self._read_data()
            raw_result = data.get(key)

        if raw_result is None:
            return None

        if not isinstance(raw_result, dict):
            raise RuntimeError(
                "Stored task result is invalid."
            )

        return self._deserialize(raw_result)

    def list_for_plan(
        self,
        plan_id: str,
    ) -> list[TaskExecutionResult]:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError("plan_id cannot be empty.")

        with self._lock:
            data = self._read_data()

        results = [
            self._deserialize(raw_result)
            for raw_result in data.values()
            if isinstance(raw_result, dict)
            and raw_result.get("plan_id")
            == cleaned_plan_id
        ]

        return sorted(
            results,
            key=lambda result: result.task_id,
        )

    def delete_plan(
        self,
        plan_id: str,
    ) -> None:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError("plan_id cannot be empty.")

        with self._lock:
            data = self._read_data()

            filtered = {
                key: value
                for key, value in data.items()
                if not (
                    isinstance(value, dict)
                    and value.get("plan_id")
                    == cleaned_plan_id
                )
            }

            self._write_data(filtered)

    @staticmethod
    def _key(
        plan_id: str,
        task_id: int,
    ) -> str:
        cleaned_plan_id = plan_id.strip()

        if not cleaned_plan_id:
            raise ValueError("plan_id cannot be empty.")

        if task_id < 1:
            raise ValueError("task_id must be positive.")

        return f"{cleaned_plan_id}:{task_id}"

    @staticmethod
    def _deserialize(
        raw_result: dict[str, Any],
    ) -> TaskExecutionResult:
        try:
            return TaskExecutionResult(
                plan_id=str(raw_result["plan_id"]),
                task_id=int(raw_result["task_id"]),
                success=bool(raw_result["success"]),
                output=str(raw_result.get("output", "")),
                error=(
                    str(raw_result["error"])
                    if raw_result.get("error")
                    is not None
                    else None
                ),
                validation_result=(
                    str(raw_result["validation_result"])
                    if raw_result.get(
                        "validation_result"
                    )
                    is not None
                    else None
                ),
                retry_count=int(
                    raw_result.get("retry_count", 0)
                ),
                created_at=str(
                    raw_result["created_at"]
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                "Stored task result contains invalid data."
            ) from exc

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
                    "Task result store must contain "
                    "a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Task result store contains invalid JSON."
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
