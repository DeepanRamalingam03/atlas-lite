from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.orchestration.directive_importer import (
    ArchitectDirectiveStatus,
    ArchitectDirectiveStore,
)
from core.orchestration.models import WorkflowRecord
from core.orchestration.observability import (
    RuntimeAlertStore,
    RuntimeHeartbeatStore,
)
from core.orchestration.roadmap import (
    RoadmapTask,
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from core.orchestration.state_store import WorkflowStateStore


@dataclass(slots=True, frozen=True)
class RuntimeControlResult:
    success: bool
    message: str


class DiscordRuntimeControls:
    """
    Discord control surface for the persistent Atlas runtime.

    Supported operations:
    - Runtime and roadmap status
    - Workflow status
    - Heartbeat health
    - Runtime alert listing and acknowledgement
    - Architect directive injection
    - Roadmap task pause and resume
    """

    def __init__(
        self,
        roadmap_store: RoadmapTaskStore | None = None,
        workflow_store: WorkflowStateStore | None = None,
        roadmap_selector: RoadmapTaskSelector | None = None,
        directive_store: ArchitectDirectiveStore | None = None,
        heartbeat_store: RuntimeHeartbeatStore | None = None,
        alert_store: RuntimeAlertStore | None = None,
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
        self.directive_store = (
            directive_store
            or ArchitectDirectiveStore()
        )
        self.heartbeat_store = (
            heartbeat_store
            or RuntimeHeartbeatStore()
        )
        self.alert_store = (
            alert_store
            or RuntimeAlertStore()
        )

    def runtime_status(
        self,
        user_id: int,
    ) -> RuntimeControlResult:
        selection = (
            self.roadmap_selector.select_next()
        )

        latest_workflow = (
            self.workflow_store.latest_for_user(
                user_id
            )
        )

        roadmap_tasks = (
            self.roadmap_store.list_all()
        )

        directives = (
            self.directive_store.list_all()
        )

        counts = {
            status: sum(
                task.status == status
                for task in roadmap_tasks
            )
            for status in RoadmapTaskStatus
        }

        pending_directives = sum(
            directive.status
            == ArchitectDirectiveStatus.PENDING
            for directive in directives
        )

        next_task = (
            (
                f"`{selection.task.task_id}` - "
                f"{selection.task.title}"
            )
            if selection.task is not None
            else "None"
        )

        workflow_line = (
            self._workflow_line(
                latest_workflow
            )
            if latest_workflow is not None
            else "No workflow recorded."
        )

        heartbeat = self.heartbeat_store.load()

        heartbeat_line = (
            self._heartbeat_summary()
            if heartbeat is not None
            else "No heartbeat recorded."
        )

        unacknowledged_alerts = len(
            self.alert_store.list_unacknowledged()
        )

        message = (
            "**Atlas Continuous Runtime**\n"
            f"Roadmap tasks: `{len(roadmap_tasks)}`\n"
            f"Pending: "
            f"`{counts[RoadmapTaskStatus.PENDING]}`\n"
            f"Running: "
            f"`{counts[RoadmapTaskStatus.RUNNING]}`\n"
            f"Completed: "
            f"`{counts[RoadmapTaskStatus.COMPLETED]}`\n"
            f"Blocked: "
            f"`{counts[RoadmapTaskStatus.BLOCKED]}`\n"
            f"Failed: "
            f"`{counts[RoadmapTaskStatus.FAILED]}`\n"
            f"Paused: "
            f"`{counts[RoadmapTaskStatus.PAUSED]}`\n"
            f"Pending directives: "
            f"`{pending_directives}`\n"
            f"Unacknowledged alerts: "
            f"`{unacknowledged_alerts}`\n"
            f"Next ready task: {next_task}\n"
            f"Latest workflow: {workflow_line}\n"
            f"Heartbeat: {heartbeat_line}\n"
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

        remaining = (
            len(tasks) - len(rendered_tasks)
        )

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
                self.workflow_store
                .latest_for_user(user_id)
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
            f"Plan ID: "
            f"`{workflow.plan_id or 'None'}`\n"
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

    def heartbeat_status(
        self,
        stale_after_seconds: float = 120.0,
    ) -> RuntimeControlResult:
        if stale_after_seconds < 1:
            raise ValueError(
                "stale_after_seconds must be at least 1."
            )

        heartbeat = self.heartbeat_store.load()

        if heartbeat is None:
            return RuntimeControlResult(
                success=False,
                message=(
                    "**Atlas Runtime Heartbeat**\n"
                    "No heartbeat has been recorded."
                ),
            )

        updated_at = datetime.fromisoformat(
            heartbeat.updated_at
        )

        now = datetime.now(timezone.utc)

        age_seconds = max(
            0.0,
            (now - updated_at).total_seconds(),
        )

        healthy = (
            heartbeat.service_status == "running"
            and age_seconds <= stale_after_seconds
        )

        health_label = (
            "HEALTHY"
            if healthy
            else "STALE OR STOPPED"
        )

        message = (
            "**Atlas Runtime Heartbeat**\n"
            f"Health: `{health_label}`\n"
            f"Service status: "
            f"`{heartbeat.service_status}`\n"
            f"Process ID: "
            f"`{heartbeat.process_id}`\n"
            f"Hostname: "
            f"`{heartbeat.hostname}`\n"
            f"Cycle count: "
            f"`{heartbeat.cycle_count}`\n"
            f"Last cycle: "
            f"`{heartbeat.last_cycle_status or 'None'}`\n"
            f"Task: "
            f"`{heartbeat.task_id or 'None'}`\n"
            f"Message: {heartbeat.message}\n"
            f"Heartbeat age: "
            f"`{age_seconds:.1f} seconds`\n"
            f"Updated: `{heartbeat.updated_at}`"
        )

        return RuntimeControlResult(
            success=healthy,
            message=message,
        )

    def alerts_status(
        self,
        limit: int = 10,
        *,
        include_acknowledged: bool = False,
    ) -> RuntimeControlResult:
        if limit < 1:
            raise ValueError(
                "limit must be at least 1."
            )

        alerts = (
            self.alert_store.list_all()
            if include_acknowledged
            else self.alert_store
            .list_unacknowledged()
        )

        if not alerts:
            return RuntimeControlResult(
                success=True,
                message=(
                    "**Atlas Runtime Alerts**\n"
                    "No active runtime alerts."
                ),
            )

        selected = alerts[-limit:]

        rendered = [
            (
                f"- `{alert.severity.upper()}` "
                f"[{alert.cycle_status}] "
                f"Task: `{alert.task_id or 'None'}`\n"
                f"  {alert.message}\n"
                f"  Created: `{alert.created_at}`"
            )
            for alert in reversed(selected)
        ]

        remaining = len(alerts) - len(selected)

        if remaining > 0:
            rendered.append(
                f"...and `{remaining}` older alert(s)."
            )

        return RuntimeControlResult(
            success=False,
            message=(
                "**Atlas Runtime Alerts**\n"
                + "\n".join(rendered)
            ),
        )

    def acknowledge_alerts(
        self,
    ) -> RuntimeControlResult:
        changed = (
            self.alert_store.acknowledge_all()
        )

        return RuntimeControlResult(
            success=True,
            message=(
                "Acknowledged "
                f"`{changed}` runtime alert(s)."
            ),
        )

    def add_directive(
        self,
        *,
        title: str,
        goal: str,
        priority: int = 100,
        depends_on: tuple[str, ...] = (),
        source: str = "discord-architect",
    ) -> RuntimeControlResult:
        cleaned_title = title.strip()
        cleaned_goal = goal.strip()

        if not cleaned_title:
            raise ValueError(
                "title cannot be empty."
            )

        if not cleaned_goal:
            raise ValueError(
                "goal cannot be empty."
            )

        if priority < 0:
            raise ValueError(
                "priority cannot be negative."
            )

        directive = self.directive_store.create(
            title=cleaned_title,
            goal=cleaned_goal,
            priority=priority,
            depends_on=depends_on,
            source=source,
        )

        return RuntimeControlResult(
            success=True,
            message=(
                "**Architect Directive Added**\n"
                f"ID: `{directive.directive_id}`\n"
                f"Priority: `{directive.priority}`\n"
                f"Title: {directive.title}\n"
                f"Goal: {directive.goal}\n"
                "Status: `pending`\n"
                "Atlas will import it during the next "
                "runtime cycle."
            ),
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
                f"`{paused.task_id}` - "
                f"{paused.title}"
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
                f"`{resumed.task_id}` - "
                f"{resumed.title}"
            ),
        )

    def retry_task(
        self,
        task_id: str,
    ) -> RuntimeControlResult:
        cleaned_task_id = task_id.strip()

        if not cleaned_task_id:
            return RuntimeControlResult(
                success=False,
                message=(
                    "Task ID cannot be empty.\n"
                    "Usage: `!retry <task-id>`"
                ),
            )

        if self.roadmap_store is None:
            return RuntimeControlResult(
                success=False,
                message=(
                    "Atlas roadmap store "
                    "is not configured."
                ),
            )

        try:
            task = (
                self.roadmap_store
                .retry_failed(
                    cleaned_task_id
                )
            )
        except KeyError:
            return RuntimeControlResult(
                success=False,
                message=(
                    "**Atlas Task Retry Failed**\n"
                    "Roadmap task was not found: "
                    f"`{cleaned_task_id}`"
                ),
            )
        except Exception as exc:
            return RuntimeControlResult(
                success=False,
                message=(
                    "**Atlas Task Retry Failed**\n"
                    f"`{type(exc).__name__}: {exc}`"
                ),
            )

        dependencies = (
            ", ".join(task.depends_on)
            if task.depends_on
            else "none"
        )

        return RuntimeControlResult(
            success=True,
            message=(
                "**Atlas Task Retry Scheduled**\n"
                f"Task: `{task.task_id}`\n"
                f"Status: `{task.status.value}`\n"
                f"Dependencies: `{dependencies}`\n\n"
                "The continuous runtime will "
                "automatically select this task "
                "when its dependencies are ready."
            ),
        )

    def _heartbeat_summary(self) -> str:
        heartbeat = self.heartbeat_store.load()

        if heartbeat is None:
            return "No heartbeat recorded."

        return (
            f"`{heartbeat.service_status}` "
            f"cycle `{heartbeat.cycle_count}` "
            f"last `{heartbeat.last_cycle_status or 'None'}` "
            f"updated `{heartbeat.updated_at}`"
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
            f"P{task.priority} - "
            f"{task.title} "
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
