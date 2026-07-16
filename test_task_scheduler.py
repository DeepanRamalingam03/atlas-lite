from __future__ import annotations

from core.planning.models import (
    ExecutionPlan,
    PlanTask,
    TaskStatus,
)
from core.planning.task_scheduler import (
    TaskScheduler,
    TaskSchedulingError,
)


plan = ExecutionPlan(goal="Build feature")

plan.add_task(
    PlanTask(
        task_id=1,
        title="Analyze",
        description="Analyze project",
    )
)

plan.add_task(
    PlanTask(
        task_id=2,
        title="Implement backend",
        description="Implement backend",
        depends_on=[1],
    )
)

plan.add_task(
    PlanTask(
        task_id=3,
        title="Implement frontend",
        description="Implement frontend",
        depends_on=[1],
    )
)

plan.add_task(
    PlanTask(
        task_id=4,
        title="Run tests",
        description="Run tests",
        depends_on=[2, 3],
    )
)

scheduler = TaskScheduler()

ready = scheduler.ready_tasks(plan)

assert [
    task.task_id
    for task in ready
] == [1]

assert scheduler.next_task(plan).task_id == 1

scheduler.mark_running(plan, 1)

assert plan.tasks[0].status == TaskStatus.RUNNING

scheduler.mark_completed(plan, 1)

assert plan.tasks[0].status == TaskStatus.COMPLETED

ready = scheduler.ready_tasks(plan)

assert {
    task.task_id
    for task in ready
} == {2, 3}

assert scheduler.next_task(plan).task_id == 2

waiting = scheduler.waiting_tasks(plan)

assert [
    task.task_id
    for task in waiting
] == [4]

scheduler.mark_running(plan, 2)
scheduler.mark_completed(plan, 2)

scheduler.mark_running(plan, 3)
scheduler.mark_failed(plan, 3)

blocked = scheduler.blocked_tasks(plan)

assert [
    task.task_id
    for task in blocked
] == [4]

assert scheduler.ready_tasks(plan) == []
assert scheduler.next_task(plan) is None

try:
    scheduler.mark_running(plan, 4)
except TaskSchedulingError:
    pass
else:
    raise AssertionError(
        "Blocked tasks must not start."
    )

try:
    scheduler.mark_completed(plan, 2)
except TaskSchedulingError:
    pass
else:
    raise AssertionError(
        "Completed tasks cannot be completed again."
    )

try:
    scheduler.mark_running(plan, 99)
except TaskSchedulingError:
    pass
else:
    raise AssertionError(
        "Missing tasks must raise an error."
    )

print("Task scheduler passed")
