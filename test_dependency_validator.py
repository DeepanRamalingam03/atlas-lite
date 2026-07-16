from core.planning.dependency_validator import (
    DependencyValidationError,
    DependencyValidator,
)
from core.planning.models import (
    ExecutionPlan,
    PlanTask,
)

validator = DependencyValidator()

plan = ExecutionPlan(goal="Demo")

plan.add_task(
    PlanTask(
        task_id=1,
        title="Task 1",
        description="",
    )
)

plan.add_task(
    PlanTask(
        task_id=2,
        title="Task 2",
        description="",
        depends_on=[1],
    )
)

validator.validate(plan)

bad_plan = ExecutionPlan(goal="Bad")

bad_plan.add_task(
    PlanTask(
        task_id=1,
        title="Task",
        description="",
        depends_on=[1],
    )
)

try:
    validator.validate(bad_plan)
except DependencyValidationError:
    pass
else:
    raise AssertionError(
        "Self dependency should fail."
    )

missing_plan = ExecutionPlan(goal="Missing")

missing_plan.add_task(
    PlanTask(
        task_id=1,
        title="Task",
        description="",
        depends_on=[99],
    )
)

try:
    validator.validate(missing_plan)
except DependencyValidationError:
    pass
else:
    raise AssertionError(
        "Missing dependency should fail."
    )

future_plan = ExecutionPlan(goal="Future")

future_plan.add_task(
    PlanTask(
        task_id=1,
        title="Task 1",
        description="",
    )
)

future_plan.add_task(
    PlanTask(
        task_id=2,
        title="Task 2",
        description="",
        depends_on=[3],
    )
)

future_plan.add_task(
    PlanTask(
        task_id=3,
        title="Task 3",
        description="",
    )
)

try:
    validator.validate(future_plan)
except DependencyValidationError:
    pass
else:
    raise AssertionError(
        "Future dependency should fail."
    )

print("Dependency validator passed")
