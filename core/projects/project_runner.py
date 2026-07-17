from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestration.roadmap import (
    RoadmapTask,
    RoadmapTaskStore,
    RoadmapStoreError,
)


@dataclass(
    slots=True,
    frozen=True,
)
class ProjectTaskDefinition:
    task_id: str
    title: str
    goal: str
    priority: int
    depends_on: tuple[str, ...]
    source_file: str


@dataclass(
    slots=True,
    frozen=True,
)
class ProjectDefinition:
    project_id: str
    name: str
    version: str
    description: str
    tasks: tuple[
        ProjectTaskDefinition,
        ...,
    ]
    project_path: Path


@dataclass(
    slots=True,
    frozen=True,
)
class ProjectImportResult:
    project_id: str
    project_name: str
    created_task_ids: tuple[str, ...]
    existing_task_ids: tuple[str, ...]
    total_tasks: int

    @property
    def created_count(self) -> int:
        return len(
            self.created_task_ids
        )

    @property
    def existing_count(self) -> int:
        return len(
            self.existing_task_ids
        )


class ProjectDefinitionError(
    RuntimeError
):
    """Raised when a project folder is invalid."""


class ProjectFolderRunner:
    """
    Validates and imports deterministic project folders into Atlas roadmap.

    Execution truth comes from JSON files. Markdown files may exist for
    human documentation, but are not parsed as executable instructions.
    """

    IDENTIFIER_PATTERN = re.compile(
        r"^[a-z0-9][a-z0-9_-]{1,63}$"
    )

    def __init__(
        self,
        roadmap_store: RoadmapTaskStore,
        *,
        projects_root: str | Path = (
            "atlas_projects"
        ),
        max_tasks: int = 100,
        max_goal_characters: int = 20_000,
    ) -> None:
        if max_tasks < 1:
            raise ValueError(
                "max_tasks must be at least 1."
            )

        if max_tasks > 500:
            raise ValueError(
                "max_tasks cannot exceed 500."
            )

        if max_goal_characters < 100:
            raise ValueError(
                "max_goal_characters must be at least 100."
            )

        self.roadmap_store = (
            roadmap_store
        )

        self.projects_root = Path(
            projects_root
        ).resolve()

        self.max_tasks = max_tasks
        self.max_goal_characters = (
            max_goal_characters
        )

        self.projects_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load_project(
        self,
        project_name: str,
    ) -> ProjectDefinition:
        project_path = (
            self._resolve_project_path(
                project_name
            )
        )

        manifest_path = (
            project_path / "project.json"
        )

        if not manifest_path.is_file():
            raise ProjectDefinitionError(
                "Project manifest is missing: "
                f"{manifest_path}"
            )

        manifest = self._read_json(
            manifest_path
        )

        project_id = self._identifier(
            manifest.get("project_id"),
            field="project_id",
        )

        name = self._required_text(
            manifest.get("name"),
            field="name",
        )

        version = self._required_text(
            manifest.get("version"),
            field="version",
        )

        description = self._required_text(
            manifest.get(
                "description",
                "No description provided.",
            ),
            field="description",
        )

        task_files = manifest.get(
            "tasks"
        )

        if not isinstance(
            task_files,
            list,
        ):
            raise ProjectDefinitionError(
                "project.json tasks must be a list."
            )

        if not task_files:
            raise ProjectDefinitionError(
                "Project must contain at least one task."
            )

        if len(task_files) > self.max_tasks:
            raise ProjectDefinitionError(
                "Project exceeds configured task limit: "
                f"{len(task_files)} > {self.max_tasks}."
            )

        definitions: list[
            ProjectTaskDefinition
        ] = []

        seen_files: set[str] = set()

        for task_file in task_files:
            if not isinstance(
                task_file,
                str,
            ):
                raise ProjectDefinitionError(
                    "Each task entry must be a filename."
                )

            cleaned_file = (
                task_file.strip()
            )

            if not cleaned_file:
                raise ProjectDefinitionError(
                    "Task filename cannot be empty."
                )

            if cleaned_file in seen_files:
                raise ProjectDefinitionError(
                    "Duplicate task file in manifest: "
                    f"{cleaned_file}"
                )

            seen_files.add(
                cleaned_file
            )

            task_path = (
                self._resolve_task_path(
                    project_path,
                    cleaned_file,
                )
            )

            definitions.append(
                self._load_task(
                    task_path=task_path,
                    source_file=cleaned_file,
                )
            )

        self._validate_task_graph(
            definitions
        )

        return ProjectDefinition(
            project_id=project_id,
            name=name,
            version=version,
            description=description,
            tasks=tuple(definitions),
            project_path=project_path,
        )

    def import_project(
        self,
        project_name: str,
    ) -> ProjectImportResult:
        project = self.load_project(
            project_name
        )

        created_ids: list[str] = []
        existing_ids: list[str] = []

        resolved_ids = {
            task.task_id: (
                self._roadmap_task_id(
                    project.project_id,
                    task.task_id,
                )
            )
            for task in project.tasks
        }

        try:
            for task in project.tasks:
                roadmap_task_id = (
                    resolved_ids[
                        task.task_id
                    ]
                )

                dependencies = tuple(
                    resolved_ids[
                        dependency
                    ]
                    for dependency
                    in task.depends_on
                )

                existing = (
                    self.roadmap_store.load(
                        roadmap_task_id
                    )
                )

                if existing is not None:
                    self._validate_existing(
                        existing=existing,
                        task=task,
                        dependencies=(
                            dependencies
                        ),
                        project=project,
                    )

                    existing_ids.append(
                        roadmap_task_id
                    )

                    continue

                created = (
                    self.roadmap_store.create(
                        title=task.title,
                        goal=self._render_goal(
                            project=project,
                            task=task,
                        ),
                        priority=task.priority,
                        depends_on=dependencies,
                        source=(
                            "project-folder:"
                            f"{project.project_id}"
                        ),
                        task_id=(
                            roadmap_task_id
                        ),
                    )
                )

                created_ids.append(
                    created.task_id
                )

        except Exception:
            self._rollback_created(
                created_ids
            )
            raise

        return ProjectImportResult(
            project_id=project.project_id,
            project_name=project.name,
            created_task_ids=tuple(
                created_ids
            ),
            existing_task_ids=tuple(
                existing_ids
            ),
            total_tasks=len(
                project.tasks
            ),
        )

    def preview(
        self,
        project_name: str,
    ) -> str:
        project = self.load_project(
            project_name
        )

        lines = [
            "**Atlas Project Preview**",
            (
                "Project ID: "
                f"`{project.project_id}`"
            ),
            (
                "Name: "
                f"`{project.name}`"
            ),
            (
                "Version: "
                f"`{project.version}`"
            ),
            (
                "Tasks: "
                f"`{len(project.tasks)}`"
            ),
            "",
        ]

        for index, task in enumerate(
            project.tasks,
            start=1,
        ):
            dependencies = (
                ", ".join(
                    task.depends_on
                )
                if task.depends_on
                else "none"
            )

            lines.extend(
                [
                    (
                        f"**{index}. "
                        f"{task.task_id} — "
                        f"{task.title}**"
                    ),
                    (
                        "Priority: "
                        f"`{task.priority}`"
                    ),
                    (
                        "Depends on: "
                        f"`{dependencies}`"
                    ),
                    "",
                ]
            )

        return "\n".join(
            lines
        ).rstrip()

    def _load_task(
        self,
        *,
        task_path: Path,
        source_file: str,
    ) -> ProjectTaskDefinition:
        payload = self._read_json(
            task_path
        )

        task_id = self._identifier(
            payload.get("task_id"),
            field="task_id",
        )

        title = self._required_text(
            payload.get("title"),
            field="title",
        )

        goal = self._required_text(
            payload.get("goal"),
            field="goal",
        )

        if (
            len(goal)
            > self.max_goal_characters
        ):
            raise ProjectDefinitionError(
                "Task goal exceeds configured "
                f"character limit: {task_id}"
            )

        priority = payload.get(
            "priority",
            100,
        )

        if (
            not isinstance(
                priority,
                int,
            )
            or isinstance(
                priority,
                bool,
            )
        ):
            raise ProjectDefinitionError(
                f"Task priority must be an integer: {task_id}"
            )

        if priority < 0:
            raise ProjectDefinitionError(
                f"Task priority cannot be negative: {task_id}"
            )

        raw_dependencies = payload.get(
            "depends_on",
            [],
        )

        if not isinstance(
            raw_dependencies,
            list,
        ):
            raise ProjectDefinitionError(
                f"depends_on must be a list: {task_id}"
            )

        dependencies: list[str] = []

        for dependency in (
            raw_dependencies
        ):
            cleaned_dependency = (
                self._identifier(
                    dependency,
                    field=(
                        f"{task_id}.depends_on"
                    ),
                )
            )

            if (
                cleaned_dependency
                in dependencies
            ):
                raise ProjectDefinitionError(
                    "Duplicate dependency "
                    f"{cleaned_dependency} "
                    f"in task {task_id}."
                )

            dependencies.append(
                cleaned_dependency
            )

        if task_id in dependencies:
            raise ProjectDefinitionError(
                f"Task cannot depend on itself: {task_id}"
            )

        return ProjectTaskDefinition(
            task_id=task_id,
            title=title,
            goal=goal,
            priority=priority,
            depends_on=tuple(
                dependencies
            ),
            source_file=source_file,
        )

    def _validate_task_graph(
        self,
        tasks: list[
            ProjectTaskDefinition
        ],
    ) -> None:
        task_ids = [
            task.task_id
            for task in tasks
        ]

        if len(task_ids) != len(
            set(task_ids)
        ):
            raise ProjectDefinitionError(
                "Project contains duplicate task IDs."
            )

        known: set[str] = set()

        for task in tasks:
            invalid_dependencies = [
                dependency
                for dependency
                in task.depends_on
                if dependency not in known
            ]

            if invalid_dependencies:
                raise ProjectDefinitionError(
                    "Task contains missing or forward "
                    f"dependencies: {task.task_id} -> "
                    + ", ".join(
                        invalid_dependencies
                    )
                )

            known.add(
                task.task_id
            )

    def _validate_existing(
        self,
        *,
        existing: RoadmapTask,
        task: ProjectTaskDefinition,
        dependencies: tuple[str, ...],
        project: ProjectDefinition,
    ) -> None:
        expected_goal = (
            self._render_goal(
                project=project,
                task=task,
            )
        )

        expected_source = (
            "project-folder:"
            f"{project.project_id}"
        )

        mismatches: list[str] = []

        if existing.title != task.title:
            mismatches.append(
                "title"
            )

        if existing.goal != expected_goal:
            mismatches.append(
                "goal"
            )

        if (
            existing.priority
            != task.priority
        ):
            mismatches.append(
                "priority"
            )

        if (
            existing.depends_on
            != dependencies
        ):
            mismatches.append(
                "dependencies"
            )

        if (
            existing.source
            != expected_source
        ):
            mismatches.append(
                "source"
            )

        if mismatches:
            raise ProjectDefinitionError(
                "Existing roadmap task conflicts "
                f"with project definition: "
                f"{existing.task_id} "
                f"({', '.join(mismatches)})"
            )

    def _rollback_created(
        self,
        created_ids: list[str],
    ) -> None:
        failures: list[str] = []

        for task_id in reversed(
            created_ids
        ):
            try:
                self.roadmap_store.delete(
                    task_id
                )
            except Exception:
                failures.append(
                    task_id
                )

        if failures:
            raise RoadmapStoreError(
                "Project import failed and rollback "
                "could not delete tasks: "
                + ", ".join(
                    failures
                )
            )

    def _resolve_project_path(
        self,
        project_name: str,
    ) -> Path:
        cleaned_name = self._identifier(
            project_name,
            field="project name",
        )

        candidate = (
            self.projects_root
            / cleaned_name
        ).resolve()

        if (
            candidate.parent
            != self.projects_root
        ):
            raise ProjectDefinitionError(
                "Project path escapes projects root."
            )

        if not candidate.is_dir():
            raise ProjectDefinitionError(
                "Project folder does not exist: "
                f"{cleaned_name}"
            )

        return candidate

    @staticmethod
    def _resolve_task_path(
        project_path: Path,
        task_file: str,
    ) -> Path:
        relative = Path(
            task_file
        )

        if relative.is_absolute():
            raise ProjectDefinitionError(
                "Task path cannot be absolute."
            )

        if ".." in relative.parts:
            raise ProjectDefinitionError(
                "Task path cannot contain parent traversal."
            )

        candidate = (
            project_path
            / relative
        ).resolve()

        tasks_root = (
            project_path / "tasks"
        ).resolve()

        try:
            candidate.relative_to(
                tasks_root
            )
        except ValueError as exc:
            raise ProjectDefinitionError(
                "Task files must be inside "
                "the project tasks folder."
            ) from exc

        if candidate.suffix.lower() != ".json":
            raise ProjectDefinitionError(
                "Task files must use .json extension."
            )

        if not candidate.is_file():
            raise ProjectDefinitionError(
                "Task file does not exist: "
                f"{task_file}"
            )

        return candidate

    @classmethod
    def _identifier(
        cls,
        value: Any,
        *,
        field: str,
    ) -> str:
        if not isinstance(
            value,
            str,
        ):
            raise ProjectDefinitionError(
                f"{field} must be a string."
            )

        cleaned = (
            value.strip().lower()
        )

        if not cls.IDENTIFIER_PATTERN.fullmatch(
            cleaned
        ):
            raise ProjectDefinitionError(
                f"Invalid {field}: {value!r}"
            )

        return cleaned

    @staticmethod
    def _required_text(
        value: Any,
        *,
        field: str,
    ) -> str:
        if not isinstance(
            value,
            str,
        ):
            raise ProjectDefinitionError(
                f"{field} must be a string."
            )

        cleaned = value.strip()

        if not cleaned:
            raise ProjectDefinitionError(
                f"{field} cannot be empty."
            )

        return cleaned

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any]:
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise ProjectDefinitionError(
                "Invalid JSON file: "
                f"{path.name}: {exc}"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ProjectDefinitionError(
                "JSON root must be an object: "
                f"{path.name}"
            )

        return payload

    @staticmethod
    def _roadmap_task_id(
        project_id: str,
        task_id: str,
    ) -> str:
        return (
            f"project-{project_id}-"
            f"{task_id}"
        )

    @staticmethod
    def _render_goal(
        *,
        project: ProjectDefinition,
        task: ProjectTaskDefinition,
    ) -> str:
        return (
            "ATLAS PROJECT TASK\n"
            "==================\n"
            f"Project ID: {project.project_id}\n"
            f"Project: {project.name}\n"
            f"Project version: {project.version}\n"
            f"Task ID: {task.task_id}\n"
            f"Task source: {task.source_file}\n\n"
            "PROJECT DESCRIPTION\n"
            "===================\n"
            f"{project.description}\n\n"
            "TASK GOAL\n"
            "=========\n"
            f"{task.goal}\n\n"
            "EXECUTION REQUIREMENTS\n"
            "======================\n"
            "- Treat this task file as authoritative.\n"
            "- Use verified Git-tracked repository evidence.\n"
            "- Preserve backward compatibility.\n"
            "- Do not create unrelated features.\n"
            "- Run targeted and regression tests.\n"
            "- Commit and push only after approval.\n"
            "- Finish this task completely before "
            "dependent project tasks begin."
        )


__all__ = [
    "ProjectDefinition",
    "ProjectDefinitionError",
    "ProjectFolderRunner",
    "ProjectImportResult",
    "ProjectTaskDefinition",
]
