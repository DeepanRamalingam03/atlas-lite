from __future__ import annotations

from dataclasses import dataclass

from core.projects.project_runner import (
    ProjectDefinitionError,
    ProjectFolderRunner,
)


@dataclass(
    slots=True,
    frozen=True,
)
class ProjectControlResult:
    success: bool
    message: str


class DiscordProjectControls:
    """
    Discord-facing adapter for deterministic Atlas project folders.

    This layer never parses free-form Markdown as executable data.
    Project and task execution truth remains in validated JSON files.
    """

    def __init__(
        self,
        runner: ProjectFolderRunner | None = None,
    ) -> None:
        self.runner = runner

    def preview_project(
        self,
        project_name: str,
    ) -> ProjectControlResult:
        cleaned_name = project_name.strip()

        if not cleaned_name:
            return ProjectControlResult(
                success=False,
                message=(
                    "Project name cannot be empty.\n"
                    "Usage: `!project <project-name>`"
                ),
            )

        if self.runner is None:
            return ProjectControlResult(
                success=False,
                message=(
                    "Atlas project-folder runner "
                    "is not configured."
                ),
            )

        try:
            preview = self.runner.preview(
                cleaned_name
            )
        except (
            ProjectDefinitionError,
            ValueError,
        ) as exc:
            return ProjectControlResult(
                success=False,
                message=(
                    "**Atlas Project Preview Failed**\n"
                    f"`{type(exc).__name__}: {exc}`"
                ),
            )
        except Exception as exc:
            return ProjectControlResult(
                success=False,
                message=(
                    "**Atlas Project Preview Failed**\n"
                    "Unexpected project-reader failure: "
                    f"`{type(exc).__name__}: {exc}`"
                ),
            )

        return ProjectControlResult(
            success=True,
            message=preview,
        )

    def run_project(
        self,
        project_name: str,
    ) -> ProjectControlResult:
        cleaned_name = project_name.strip()

        if not cleaned_name:
            return ProjectControlResult(
                success=False,
                message=(
                    "Project name cannot be empty.\n"
                    "Usage: `!runproject <project-name>`"
                ),
            )

        if self.runner is None:
            return ProjectControlResult(
                success=False,
                message=(
                    "Atlas project-folder runner "
                    "is not configured."
                ),
            )

        try:
            result = self.runner.import_project(
                cleaned_name
            )
        except (
            ProjectDefinitionError,
            ValueError,
        ) as exc:
            return ProjectControlResult(
                success=False,
                message=(
                    "**Atlas Project Import Failed**\n"
                    f"`{type(exc).__name__}: {exc}`"
                ),
            )
        except Exception as exc:
            return ProjectControlResult(
                success=False,
                message=(
                    "**Atlas Project Import Failed**\n"
                    "Unexpected project-import failure: "
                    f"`{type(exc).__name__}: {exc}`"
                ),
            )

        created = (
            ", ".join(
                result.created_task_ids
            )
            if result.created_task_ids
            else "none"
        )

        existing = (
            ", ".join(
                result.existing_task_ids
            )
            if result.existing_task_ids
            else "none"
        )

        if result.created_count:
            state_message = (
                "Project tasks were imported. "
                "The continuous runtime can now "
                "select the first dependency-ready task."
            )
        else:
            state_message = (
                "No duplicate tasks were created. "
                "All project tasks already exist "
                "in the roadmap."
            )

        message = (
            "**Atlas Project Imported**\n"
            f"Project ID: `{result.project_id}`\n"
            f"Project: `{result.project_name}`\n"
            f"Total tasks: `{result.total_tasks}`\n"
            f"Created: `{result.created_count}`\n"
            f"Already existing: `{result.existing_count}`\n"
            f"Created task IDs: `{created}`\n"
            f"Existing task IDs: `{existing}`\n\n"
            f"{state_message}"
        )

        return ProjectControlResult(
            success=True,
            message=message,
        )


__all__ = [
    "DiscordProjectControls",
    "ProjectControlResult",
]
