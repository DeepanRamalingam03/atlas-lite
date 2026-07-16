from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class StagedFileChange:
    relative_path: str
    staged_path: str
    original_exists: bool
    original_hash: str | None
    staged_hash: str
    size_bytes: int


class WorkspaceSecurityError(PermissionError):
    """Raised when a workspace operation violates safety rules."""


class SafeWorkspace:
    """
    Stages proposed project file changes without modifying the project.

    Security rules:
    - Paths must remain inside the project root.
    - Paths must remain inside the staging root.
    - Secrets, keys, Git internals, virtual environments, caches,
      databases, and Atlas internal state are blocked.
    - Source files are copied to staging before modification.
    """

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
        staging_root: str | Path = ".atlas_staging",
        max_file_bytes: int = 500_000,
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

        staging_path = Path(staging_root)

        if staging_path.is_absolute():
            self.staging_root = staging_path.resolve()
        else:
            self.staging_root = (
                self.project_root / staging_path
            ).resolve()

        self._ensure_inside_project(
            self.staging_root
        )

        self.max_file_bytes = max_file_bytes

        self.staging_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def prepare(self) -> None:
        """
        Reset the staging workspace and recreate it.
        """

        if self.staging_root.exists():
            shutil.rmtree(self.staging_root)

        self.staging_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def stage_existing_file(
        self,
        relative_path: str | Path,
    ) -> Path:
        source_path = self._resolve_project_path(
            relative_path
        )

        self._ensure_allowed(source_path)

        if not source_path.exists():
            raise FileNotFoundError(
                f"Project file does not exist: {relative_path}"
            )

        if not source_path.is_file():
            raise IsADirectoryError(
                f"Project path is not a file: {relative_path}"
            )

        if source_path.stat().st_size > self.max_file_bytes:
            raise ValueError(
                f"Project file exceeds {self.max_file_bytes} bytes: "
                f"{relative_path}"
            )

        destination = self._resolve_staging_path(
            relative_path
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            source_path,
            destination,
        )

        return destination

    def write_text(
        self,
        relative_path: str | Path,
        content: str,
    ) -> StagedFileChange:
        if not isinstance(content, str):
            raise TypeError(
                "Workspace content must be text."
            )

        encoded_content = content.encode("utf-8")

        if len(encoded_content) > self.max_file_bytes:
            raise ValueError(
                f"Staged content exceeds {self.max_file_bytes} bytes."
            )

        project_path = self._resolve_project_path(
            relative_path
        )
        staged_path = self._resolve_staging_path(
            relative_path
        )

        self._ensure_allowed(project_path)

        original_exists = project_path.exists()

        if original_exists and not project_path.is_file():
            raise IsADirectoryError(
                f"Project path is not a file: {relative_path}"
            )

        original_hash = (
            self._hash_file(project_path)
            if original_exists
            else None
        )

        staged_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = staged_path.with_suffix(
            staged_path.suffix + ".tmp"
        )

        temporary_path.write_text(
            content,
            encoding="utf-8",
        )

        temporary_path.replace(staged_path)

        return StagedFileChange(
            relative_path=str(
                project_path.relative_to(
                    self.project_root
                )
            ),
            staged_path=str(staged_path),
            original_exists=original_exists,
            original_hash=original_hash,
            staged_hash=self._hash_file(staged_path),
            size_bytes=len(encoded_content),
        )

    def read_staged(
        self,
        relative_path: str | Path,
    ) -> str:
        staged_path = self._resolve_staging_path(
            relative_path
        )

        if not staged_path.exists():
            raise FileNotFoundError(
                f"Staged file does not exist: {relative_path}"
            )

        if not staged_path.is_file():
            raise IsADirectoryError(
                f"Staged path is not a file: {relative_path}"
            )

        return staged_path.read_text(
            encoding="utf-8"
        )

    def list_staged_files(self) -> list[str]:
        if not self.staging_root.exists():
            return []

        return sorted(
            str(path.relative_to(self.staging_root))
            for path in self.staging_root.rglob("*")
            if path.is_file()
            and not path.name.endswith(".tmp")
        )

    def discard(self) -> None:
        self.prepare()

    def _resolve_project_path(
        self,
        relative_path: str | Path,
    ) -> Path:
        requested = Path(relative_path)

        if requested.is_absolute():
            raise WorkspaceSecurityError(
                "Only project-relative paths are allowed."
            )

        resolved = (
            self.project_root / requested
        ).resolve()

        self._ensure_inside_project(resolved)

        return resolved

    def _resolve_staging_path(
        self,
        relative_path: str | Path,
    ) -> Path:
        requested = Path(relative_path)

        if requested.is_absolute():
            raise WorkspaceSecurityError(
                "Only staging-relative paths are allowed."
            )

        resolved = (
            self.staging_root / requested
        ).resolve()

        try:
            resolved.relative_to(
                self.staging_root
            )
        except ValueError as exc:
            raise WorkspaceSecurityError(
                "Requested path escapes the staging workspace."
            ) from exc

        return resolved

    def _ensure_inside_project(
        self,
        path: Path,
    ) -> None:
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise WorkspaceSecurityError(
                "Requested path escapes the project root."
            ) from exc

    def _ensure_allowed(
        self,
        path: Path,
    ) -> None:
        relative_path = path.relative_to(
            self.project_root
        )

        if any(
            part in self.DEFAULT_EXCLUDED_DIRECTORIES
            for part in relative_path.parts
        ):
            raise WorkspaceSecurityError(
                f"Excluded directory is blocked: {relative_path}"
            )

        if path.name in self.DEFAULT_EXCLUDED_FILES:
            raise WorkspaceSecurityError(
                f"Protected file is blocked: {relative_path}"
            )

        if path.name.startswith(".env."):
            raise WorkspaceSecurityError(
                f"Environment file is blocked: {relative_path}"
            )

        if path.suffix.lower() in self.BLOCKED_SUFFIXES:
            raise WorkspaceSecurityError(
                f"Sensitive or binary file is blocked: {relative_path}"
            )

    @staticmethod
    def _hash_file(
        path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as source:
            for chunk in iter(
                lambda: source.read(65_536),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()
