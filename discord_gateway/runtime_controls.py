from __future__ import annotations

from dataclasses import dataclass

from core.orchestration.models import (
    WorkflowRecord,
)
from core.orchestration.roadmap import (
    RoadmapTask,
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)


@dataclass(slots=True, frozen=True)
class RuntimeControlResult:
    success: bool
    message: str


class DiscordRuntimeControls:
    """
    Read and control the persistent Atlas runtime through Discord.

    Supported operations:
    - runtime status
    - roadmap summary
    - workflow summary
    - pause a pending or running roadmap task
    - resume a paused, blocked, or failed roadmap task
    """

    def __init__(
        self,
        roadmap_store: RoadmapTaskStore | None = None,
        workflow_store: WorkflowStateStore | None = None,
        roadmap_selector: RoadmapTaskSelector | None = None,
    ) -> None:
        self.roadmap_store = (
            roadmap_store or RoadmapTaskStore()
        )
        self.workflow_store = (
            workflow_store or WorkflowStateStore()
        )
        self.roadmap_selector = (
            roadmap_selector
            or RoadmapTaskSelector(
                self.roadmap_store
            )
        )

    def runtime_status(
        self,
        user_id: int,
    ) -> RuntimeControlResult:
        selection = self.roadmap_selector.select_next()
        latest_workflow = (
            self.workflow_store.latest_for_user(
                user_id
            )
        )

        roadmap_tasks = (
            self.roadmap_store.list_all()
        )

        counts = {
            status: sum(
                task.status == status
                for task in roadmap_tasks
            )
            for status in RoadmapTaskStatus
        }

        next_task = (
            (
                f"`{selection.task.task_id}` - "
                f"{selection.task.title}"
            )
            if selection.task is not None
            else "None"
        )

        workflow_line = (
            self._workflow_line(latest_workflow)
            if latest_workflow is not None
            else "No workflow recorded."
        )

        message = (
            "**Atlas Continuous Runtime**\n"
            f"Roadmap tasks: `{len(roadmap_tasks)}`\n"
            f"Pending: `{counts[RoadmapTaskStatus.PENDING]}`\n"
            f"Running: `{counts[RoadmapTaskStatus.RUNNING]}`\n"
            f"Completed: `{counts[RoadmapTaskStatus.COMPLETED]}`\n"
            f"Blocked: `{counts[RoadmapTaskStatus.BLOCKED]}`\n"
            f"Failed: `{counts[RoadmapTaskStatus.FAILED]}`\n"
            f"Paused: `{counts[RoadmapTaskStatus.PAUSED]}`\n"
            f"Next ready task: {next_task}\n"
            f"Latest workflow: {workflow_line}\n"
            f"Selector: {selection.message}"
        )

        return RuntimeControlResult(
            success=True,
            message=message,
        )

    def roadmap_status(
        self,
        limit: int = 10,
    ) -> RuntimeControlResult:
        if limit < 1:
            raise ValueError(
                "limit must be at least 1."
            )

        tasks = self.roadmap_store.list_all()

        if not tasks:
            return RuntimeControlResult(
                success=True,
                message=(
                    "**Atlas Roadmap**\n"
                    "No approved roadmap tasks exist.\n"
                    "Atlas will not create random work."
                ),
            )

        rendered_tasks = [
            self._task_line(task)
            for task in tasks[:limit]
        ]

        remaining = len(tasks) - len(rendered_tasks)

        if remaining > 0:
            rendered_tasks.append(
                f"...and `{remaining}` more task(s)."
            )

        return RuntimeControlResult(
            success=True,
            message=(
                "**Atlas Roadmap**\n"
                + "\n".join(rendered_tasks)
            ),
        )

    def workflow_status(
        self,
        user_id: int,
        workflow_id: str | None = None,
    ) -> RuntimeControlResult:
        if workflow_id is not None:
            cleaned_workflow_id = (
                workflow_id.strip()
            )

            if not cleaned_workflow_id:
                raise ValueError(
                    "workflow_id cannot be empty."
                )

            workflow = self.workflow_store.load(
                cleaned_workflow_id
            )
        else:
            workflow = (
                self.workflow_store.latest_for_user(
                    user_id
                )
            )

        if workflow is None:
            return RuntimeControlResult(
                success=False,
                message=(
                    "No matching Atlas workflow was found."
                ),
            )

        message = (
            "**Atlas Workflow**\n"
            f"ID: `{workflow.workflow_id}`\n"
            f"Status: `{workflow.status.value}`\n"
            f"Goal: {workflow.goal}\n"
            f"Plan ID: `{workflow.plan_id or 'None'}`\n"
            f"Current task: "
            f"`{workflow.current_task_id or 'None'}`\n"
            f"Summary: {workflow.summary}\n"
            f"Error: {workflow.error or 'None'}\n"
            f"Updated: `{workflow.updated_at}`"
        )

        return RuntimeControlResult(
            success=True,
            message=message,
        )

    def pause_task(
        self,
        task_id: str,
    ) -> RuntimeControlResult:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            raise ValueError(
                "task_id cannot be empty."
            )

        task = self.roadmap_store.require(
            cleaned_task_id
        )

        if task.status not in {
            RoadmapTaskStatus.PENDING,
            RoadmapTaskStatus.RUNNING,
            RoadmapTaskStatus.BLOCKED,
        }:
            return RuntimeControlResult(
                success=False,
                message=(
                    "Task cannot be paused from status "
                    f"`{task.status.value}`."
                ),
            )

        paused = self.roadmap_store.update_status(
            cleaned_task_id,
            RoadmapTaskStatus.PAUSED,
        )

        return RuntimeControlResult(
            success=True,
            message=(
                "Paused roadmap task "
                f"`{paused.task_id}` - {paused.title}"
            ),
        )

    def resume_task(
        self,
        task_id: str,
    ) -> RuntimeControlResult:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            raise ValueError(
                "task_id cannot be empty."
            )

        task = self.roadmap_store.require(
            cleaned_task_id
        )

        if task.status not in {
            RoadmapTaskStatus.PAUSED,
            RoadmapTaskStatus.BLOCKED,
            RoadmapTaskStatus.FAILED,
        }:
            return RuntimeControlResult(
                success=False,
                message=(
                    "Task cannot be resumed from status "
                    f"`{task.status.value}`."
                ),
            )

        resumed = self.roadmap_store.update_status(
            cleaned_task_id,
            RoadmapTaskStatus.PENDING,
        )

        return RuntimeControlResult(
            success=True,
            message=(
                "Resumed roadmap task "
                f"`{resumed.task_id}` - {resumed.title}"
            ),
        )

    @staticmethod
    def _task_line(
        task: RoadmapTask,
    ) -> str:
        dependency_text = (
            ", ".join(task.depends_on)
            if task.depends_on
            else "none"
        )

        blocker = (
            f" | Blocker: {task.blocker_reason}"
            if task.blocker_reason
            else ""
        )

        return (
            f"- `{task.task_id}` "
            f"[{task.status.value}] "
            f"P{task.priority} - {task.title} "
            f"| Depends: {dependency_text}"
            f"{blocker}"
        )

    @staticmethod
    def _workflow_line(
        workflow: WorkflowRecord,
    ) -> str:
        return (
            f"`{workflow.workflow_id}` "
            f"[{workflow.status.value}] "
            f"{workflow.summary}"
        )
