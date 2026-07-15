from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.file_change import FileChange


class WorkspaceWriter:
    """
    Safely writes proposed AI-generated files into an isolated staging workspace.

    The real project files are not modified by this class.
    """

    def __init__(self, staging_root: str | Path = ".atlas_staging") -> None:
        self.staging_root = Path(staging_root).resolve()

    def prepare(self) -> Path:
        """
        Create the staging workspace if it does not already exist.
        """
        self.staging_root.mkdir(parents=True, exist_ok=True)
        return self.staging_root

    def clear(self) -> None:
        """
        Remove all staged files while preserving the staging root directory.
        """
        if not self.staging_root.exists():
            return

        for path in sorted(
            self.staging_root.rglob("*"),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    def write_changes(self, changes: list[FileChange]) -> list[Path]:
        """
        Atomically write validated file changes into the staging workspace.
        """
        if not changes:
            raise ValueError("At least one file change is required.")

        self.prepare()
        written_paths: list[Path] = []

        for change in changes:
            destination = self._safe_destination(change.path)
            destination.parent.mkdir(parents=True, exist_ok=True)

            self._atomic_write(
                destination=destination,
                content=change.content,
            )

            written_paths.append(destination)

        return written_paths

    def _safe_destination(self, relative_path: str) -> Path:
        """
        Resolve a relative file path and prevent writes outside staging_root.
        """
        destination = (self.staging_root / relative_path).resolve()

        try:
            destination.relative_to(self.staging_root)
        except ValueError as exc:
            raise ValueError(
                f"Unsafe workspace path rejected: {relative_path}"
            ) from exc

        return destination

    @staticmethod
    def _atomic_write(destination: Path, content: str) -> None:
        """
        Write to a temporary file and replace the destination atomically.
        """
        temp_file_path: str | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                delete=False,
            ) as temp_file:
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_file_path = temp_file.name

            os.replace(temp_file_path, destination)

        except Exception:
            if temp_file_path:
                temp_path = Path(temp_file_path)
                if temp_path.exists():
                    temp_path.unlink()

            raise
