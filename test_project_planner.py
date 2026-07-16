from __future__ import annotations

from core.planning.models import TaskStatus
from core.planning.planner import ProjectPlanner

planner = ProjectPlanner()

plan = planner.create_plan(
    "Add JWT authentication"
)

assert plan.goal == "Add JWT authentication"
assert len(plan.tasks) == 8

task_ids = [
    task.task_id
    for task in plan.tasks
]

assert task_ids == list(range(1, 9))

assert plan.tasks[0].title == (
    "Analyze current implementation"
)

assert plan.tasks[0].status == TaskStatus.PENDING
assert plan.tasks[0].depends_on == []

for task in plan.tasks:
    for dep in task.depends_on:
        assert dep < task.task_id

assert len(plan.pending_tasks) == len(plan.tasks)
assert plan.completed_tasks == []

try:
    planner.create_plan("")
except ValueError:
    pass
else:
    raise AssertionError(
        "Planner must reject an empty goal."
    )

print("Project planner passed")
