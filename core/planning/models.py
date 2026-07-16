from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class PlanTask:
    task_id: int
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    depends_on: List[int] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionPlan:
    goal: str
    tasks: List[PlanTask] = field(default_factory=list)

    def add_task(self, task: PlanTask) -> None:
        self.tasks.append(task)

    @property
    def pending_tasks(self) -> List[PlanTask]:
        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.PENDING
        ]

    @property
    def completed_tasks(self) -> List[PlanTask]:
        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.COMPLETED
        ]
