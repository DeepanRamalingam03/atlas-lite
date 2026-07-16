from __future__ import annotations

from core.planning.task_decomposer import (
    TaskDecomposer,
)

decomposer = TaskDecomposer()

jwt_tasks = decomposer.decompose(
    "Add JWT authentication"
)

jwt_titles = [
    task.title
    for task in jwt_tasks
]

assert jwt_titles == [
    "Analyze current implementation",
    "Define implementation scope",
    "Design authentication changes",
    "Implement authentication components",
    "Add or update automated tests",
    "Run deterministic validation",
    "Review implementation",
    "Prepare changes for human approval",
]

assert jwt_tasks[1].depends_on_indexes == (0,)
assert jwt_tasks[3].depends_on_indexes == (2,)

for i in range(1, len(jwt_tasks)):
    deps = jwt_tasks[i].depends_on_indexes
    if deps:
        assert max(deps) < i

discord_tasks = decomposer.decompose(
    "Modify Discord ask command"
)

discord_titles = [
    task.title
    for task in discord_tasks
]

assert "Design Discord integration changes" in discord_titles
assert "Implement Discord changes" in discord_titles

general_tasks = decomposer.decompose(
    "Create a project status exporter"
)

general_titles = [
    task.title
    for task in general_tasks
]

assert "Implement requested changes" in general_titles

try:
    decomposer.decompose("   ")
except ValueError:
    pass
else:
    raise AssertionError(
        "Empty goals must be rejected."
    )

print("Task decomposer passed")
