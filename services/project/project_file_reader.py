from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class ProjectFileContent:
    path: str
    content: str
    size_bytes: int
    truncated: bool


class ProjectFileReader:
    """
    Safely reads approved project text files.

    Security rules:
    - Files must remain inside the configured project root.
    - Secrets, private keys, Git internals, virtual environments,
      caches, generated files, and temporary Atlas workspaces are blocked.
    - Binary and unsupported file types are rejected.
    - Large files are truncated to a configured byte limit.
    """

    DEFAULT_ALLOWED_EXTENSIONS = {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".conf",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".html",
        ".css",
        ".scss",
        ".sql",
        ".sh",
    }

    DEFAULT_EXCLUDED_DIRECTORIES = {
        ".git",
        ".github",
        ".idea",
        ".vscode",
        ".atlas_data",
        ".atlas_staging",
        ".atlas_apply_project",
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
        "id_rsa",
        "id_ed25519",
    }

    BLOCKED_SUFFIXES = {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".crt",
        ".cer",
        ".der",
        ".sqlite",
        ".db",
        ".pyc",
    }

    def __init__(
        self,
        project_root: str | Path,
        max_file_bytes: int = 100_000,
        allowed_extensions: set[str] | None = None,
        excluded_directories: set[str] | None = None,
        excluded_files: set[str] | None = None,
    ) -> None:
        if max_file_bytes < 1_000:
            raise ValueError(
                "max_file_bytes must be at least 1000."
            )

        self.project_root = Path(project_root).resolve()

        if not self.project_root.exists():
            raise FileNotFoundError(
                f"Project root does not exist: {self.project_root}"
            )

        if not self.project_root.is_dir():
            raise NotADirectoryError(
                f"Project root is not a directory: {self.project_root}"
            )

        self.max_file_bytes = max_file_bytes
        self.allowed_extensions = (
            allowed_extensions
            or self.DEFAULT_ALLOWED_EXTENSIONS.copy()
        )
        self.excluded_directories = (
            excluded_directories
            or self.DEFAULT_EXCLUDED_DIRECTORIES.copy()
        )
        self.excluded_files = (
            excluded_files
            or self.DEFAULT_EXCLUDED_FILES.copy()
        )

    def read(
        self,
        relative_path: str | Path,
    ) -> ProjectFileContent:
        requested_path = Path(relative_path)

        if requested_path.is_absolute():
            raise ValueError(
                "Only project-relative file paths are allowed."
            )

        resolved_path = (
            self.project_root / requested_path
        ).resolve()

        self._ensure_inside_project(resolved_path)
        self._ensure_allowed(resolved_path)

        if not resolved_path.exists():
            raise FileNotFoundError(
                f"Project file does not exist: {relative_path}"
            )

        if not resolved_path.is_file():
            raise IsADirectoryError(
                f"Requested path is not a file: {relative_path}"
            )

        raw_data = resolved_path.read_bytes()
        original_size = len(raw_data)
        truncated = original_size > self.max_file_bytes

        selected_data = raw_data[: self.max_file_bytes]

        try:
            content = selected_data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Project file is not valid UTF-8 text: {relative_path}"
            ) from exc

        return ProjectFileContent(
            path=str(
                resolved_path.relative_to(self.project_root)
            ),
            content=content,
            size_bytes=original_size,
            truncated=truncated,
        )

    def read_many(
        self,
        relative_paths: list[str | Path],
        max_files: int = 20,
    ) -> list[ProjectFileContent]:
        if max_files < 1:
            raise ValueError("max_files must be at least 1.")

        if len(relative_paths) > max_files:
            raise ValueError(
                f"Cannot read more than {max_files} files at once."
            )

        return [
            self.read(relative_path)
            for relative_path in relative_paths
        ]

    def _ensure_inside_project(
        self,
        resolved_path: Path,
    ) -> None:
        try:
            resolved_path.relative_to(self.project_root)
        except ValueError as exc:
            raise PermissionError(
                "Requested path escapes the project root."
            ) from exc

    def _ensure_allowed(
        self,
        resolved_path: Path,
    ) -> None:
        relative_path = resolved_path.relative_to(
            self.project_root
        )

        if any(
            part in self.excluded_directories
            for part in relative_path.parts
        ):
            raise PermissionError(
                f"Reading excluded directory is blocked: "
                f"{relative_path}"
            )

        if resolved_path.name in self.excluded_files:
            raise PermissionError(
                f"Reading protected file is blocked: "
                f"{relative_path}"
            )

        if resolved_path.name.startswith(".env."):
            raise PermissionError(
                f"Reading environment secret files is blocked: "
                f"{relative_path}"
            )

        if resolved_path.suffix.lower() in self.BLOCKED_SUFFIXES:
            raise PermissionError(
                f"Reading sensitive or binary file type is blocked: "
                f"{relative_path}"
            )

        if (
            resolved_path.suffix.lower()
            not in self.allowed_extensions
        ):
            raise ValueError(
                f"Unsupported project file type: "
                f"{resolved_path.suffix or '<no extension>'}"
            )
