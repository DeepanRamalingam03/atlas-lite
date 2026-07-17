from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from services.project.project_context_builder import (
    ProjectContextBuilder,
)
from services.project.relevant_file_context_service import (
    RelevantFileContextService,
)


class RepositoryGroundingError(RuntimeError):
    """Raised when Atlas cannot prove the real repository state."""


@dataclass(slots=True, frozen=True)
class RepositoryGrounding:
    project_root: Path
    tracked_files: tuple[str, ...]
    python_files: tuple[str, ...]
    test_files: tuple[str, ...]
    repository_context: str
    relevant_file_context: str
    rendered_context: str

    @property
    def tracked_file_count(self) -> int:
        return len(self.tracked_files)

    @property
    def python_file_count(self) -> int:
        return len(self.python_files)

    @property
    def test_file_count(self) -> int:
        return len(self.test_files)


class RepositoryGroundingService:
    """
    Builds verified repository evidence for autonomous development prompts.

    Git-tracked files are the source of truth. Existing project-context
    services add structure, symbol indexing, and selected file contents.

    Atlas must fail clearly rather than tell the worker that an implemented
    repository is empty or documentation-only.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        context_builder: ProjectContextBuilder | None = None,
        relevant_context_service: (
            RelevantFileContextService | None
        ) = None,
        git_timeout_seconds: int = 30,
        max_manifest_files: int = 500,
    ) -> None:
        if git_timeout_seconds < 1:
            raise ValueError(
                "git_timeout_seconds must be at least 1."
            )

        if max_manifest_files < 1:
            raise ValueError(
                "max_manifest_files must be at least 1."
            )

        self.project_root = Path(
            project_root
        ).resolve()

        self.context_builder = (
            context_builder
            or ProjectContextBuilder()
        )

        self.relevant_context_service = (
            relevant_context_service
            or RelevantFileContextService(
                project_root=self.project_root,
            )
        )

        self.git_timeout_seconds = (
            git_timeout_seconds
        )

        self.max_manifest_files = (
            max_manifest_files
        )

    def build(
        self,
        request: str,
    ) -> RepositoryGrounding:
        cleaned_request = request.strip()

        if not cleaned_request:
            raise ValueError(
                "Request cannot be empty."
            )

        self._validate_project_root()

        tracked_files = self._tracked_files()

        if not tracked_files:
            raise RepositoryGroundingError(
                "Git reported zero tracked files. "
                "Atlas cannot safely ground this task."
            )

        python_files = tuple(
            path
            for path in tracked_files
            if path.endswith(".py")
        )

        test_files = tuple(
            path
            for path in python_files
            if (
                Path(path).name.startswith(
                    "test_"
                )
                or "/test_" in path
            )
        )

        repository_context = (
            self.context_builder.build(
                self.project_root
            )
        ).strip()

        if not repository_context:
            raise RepositoryGroundingError(
                "Repository context builder "
                "returned empty context."
            )

        relevant_context = (
            self.relevant_context_service
            .build(cleaned_request)
        )

        rendered_relevant_context = (
            relevant_context
            .rendered_context
            .strip()
        )

        rendered = self._render(
            request=cleaned_request,
            tracked_files=tracked_files,
            python_files=python_files,
            test_files=test_files,
            repository_context=(
                repository_context
            ),
            relevant_file_context=(
                rendered_relevant_context
            ),
        )

        return RepositoryGrounding(
            project_root=self.project_root,
            tracked_files=tracked_files,
            python_files=python_files,
            test_files=test_files,
            repository_context=(
                repository_context
            ),
            relevant_file_context=(
                rendered_relevant_context
            ),
            rendered_context=rendered,
        )

    def _validate_project_root(
        self,
    ) -> None:
        if not self.project_root.exists():
            raise RepositoryGroundingError(
                "Project root does not exist: "
                f"{self.project_root}"
            )

        if not self.project_root.is_dir():
            raise RepositoryGroundingError(
                "Project root is not a directory: "
                f"{self.project_root}"
            )

        if not (
            self.project_root / ".git"
        ).exists():
            raise RepositoryGroundingError(
                "Project root is not a Git repository: "
                f"{self.project_root}"
            )

    def _tracked_files(
        self,
    ) -> tuple[str, ...]:
        completed = subprocess.run(
            [
                "git",
                "ls-files",
            ],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=self.git_timeout_seconds,
            check=False,
        )

        if completed.returncode != 0:
            raise RepositoryGroundingError(
                "Unable to read Git-tracked files.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        tracked_files = tuple(
            sorted(
                line.strip()
                for line in (
                    completed.stdout
                    .splitlines()
                )
                if line.strip()
            )
        )

        return tracked_files

    def _render(
        self,
        *,
        request: str,
        tracked_files: tuple[str, ...],
        python_files: tuple[str, ...],
        test_files: tuple[str, ...],
        repository_context: str,
        relevant_file_context: str,
    ) -> str:
        manifest_files = tracked_files[
            : self.max_manifest_files
        ]

        manifest = "\n".join(
            f"- {path}"
            for path in manifest_files
        )

        if (
            len(tracked_files)
            > self.max_manifest_files
        ):
            manifest += (
                "\n- ... "
                f"{len(tracked_files) - self.max_manifest_files} "
                "additional tracked files omitted "
                "from this rendered manifest."
            )

        repository_classification = (
            "implemented Python repository"
            if python_files
            else (
                "repository with no Git-tracked "
                "Python files"
            )
        )

        sections = [
            "VERIFIED REPOSITORY GROUNDING",
            "=============================",
            f"Task request: {request}",
            (
                "Evidence source: "
                "git ls-files from the active "
                "project repository."
            ),
            (
                "Repository classification: "
                f"{repository_classification}"
            ),
            (
                "Tracked file count: "
                f"{len(tracked_files)}"
            ),
            (
                "Tracked Python file count: "
                f"{len(python_files)}"
            ),
            (
                "Tracked test file count: "
                f"{len(test_files)}"
            ),
            "",
            "GROUNDING RULES",
            "---------------",
            (
                "- Treat the verified counts and "
                "paths below as repository facts."
            ),
            (
                "- Do not claim that the repository "
                "has no implementation when tracked "
                "source files exist."
            ),
            (
                "- Do not invent paths, modules, "
                "commands, environment variables, "
                "or frameworks."
            ),
            (
                "- Distinguish the project repository "
                "from the temporary staging workspace."
            ),
            (
                "- A staging message saying that no "
                "Python files were changed does not "
                "mean the repository has no Python code."
            ),
            "",
            "GIT-TRACKED FILE MANIFEST",
            "-------------------------",
            manifest,
            "",
            "PROJECT STRUCTURE AND SYMBOL INDEX",
            "----------------------------------",
            repository_context,
            "",
            "REQUEST-RELEVANT FILE CONTENT",
            "-----------------------------",
            (
                relevant_file_context
                or (
                    "No relevant file content "
                    "was available."
                )
            ),
        ]

        return "\n".join(sections).strip()


__all__ = [
    "RepositoryGrounding",
    "RepositoryGroundingError",
    "RepositoryGroundingService",
]
