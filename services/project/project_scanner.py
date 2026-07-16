from __future__ import annotations

from pathlib import Path


class ProjectScanner:
    """
    Builds a safe repository file index.

    Generated files, virtual environments, Git internals, secrets,
    caches, and Atlas temporary workspaces are excluded.
    """

    DEFAULT_EXCLUDED_DIRECTORIES = {
        ".git",
        ".github",
        ".idea",
        ".vscode",
        ".atlas_data",
        ".atlas_staging",
        ".atlas_apply_project",
        ".atlas_memory_test",
        ".atlas_manager_test",
        ".atlas_manager_review_test",
        ".atlas_constitution_test",
        ".atlas_project_scanner_test",
        ".atlas_project_indexer_test",
        ".atlas_project_context_test",
        ".atlas_context_manager_test",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }

    DEFAULT_EXCLUDED_FILES = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
    }

    def __init__(
        self,
        excluded_directories: set[str] | None = None,
        excluded_files: set[str] | None = None,
        max_files: int = 2_000,
    ) -> None:
        if max_files < 1:
            raise ValueError("max_files must be at least 1.")

        self.excluded_directories = (
            excluded_directories
            or self.DEFAULT_EXCLUDED_DIRECTORIES.copy()
        )
        self.excluded_files = (
            excluded_files
            or self.DEFAULT_EXCLUDED_FILES.copy()
        )
        self.max_files = max_files

    def scan(self, root: str | Path) -> str:
        root_path = Path(root).resolve()

        if not root_path.exists():
            raise FileNotFoundError(
                f"Project root does not exist: {root_path}"
            )

        if not root_path.is_dir():
            raise NotADirectoryError(
                f"Project root is not a directory: {root_path}"
            )

        lines: list[str] = []

        for path in sorted(root_path.rglob("*")):
            if path.is_dir():
                continue

            if self._is_excluded(path, root_path):
                continue

            try:
                relative = path.relative_to(root_path)
            except ValueError:
                relative = path

            lines.append(str(relative))

            if len(lines) >= self.max_files:
                lines.append(
                    "[Project file index truncated at "
                    f"{self.max_files} files]"
                )
                break

        return "\n".join(lines)

    def _is_excluded(
        self,
        path: Path,
        root: Path,
    ) -> bool:
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            relative_parts = path.parts

        if any(
            part in self.excluded_directories
            for part in relative_parts
        ):
            return True

        if path.name in self.excluded_files:
            return True

        if path.name.startswith(".env."):
            return True

        return False
