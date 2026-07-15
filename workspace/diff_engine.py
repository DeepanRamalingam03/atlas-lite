from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ChangeType(str, Enum):
    NEW = "new"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass(slots=True, frozen=True)
class FileDiff:
    relative_path: str
    change_type: ChangeType
    staged_hash: str
    project_hash: str | None


@dataclass(slots=True)
class DiffPlan:
    files: list[FileDiff]

    @property
    def new_files(self) -> list[FileDiff]:
        return [
            item
            for item in self.files
            if item.change_type is ChangeType.NEW
        ]

    @property
    def modified_files(self) -> list[FileDiff]:
        return [
            item
            for item in self.files
            if item.change_type is ChangeType.MODIFIED
        ]

    @property
    def unchanged_files(self) -> list[FileDiff]:
        return [
            item
            for item in self.files
            if item.change_type is ChangeType.UNCHANGED
        ]

    @property
    def actionable_files(self) -> list[FileDiff]:
        return [
            item
            for item in self.files
            if item.change_type is not ChangeType.UNCHANGED
        ]

    @property
    def has_changes(self) -> bool:
        return bool(self.actionable_files)


class WorkspaceDiffEngine:
    """
    Compares staged files against the real project workspace.

    This class is read-only. It never modifies project or staging files.
    """

    def __init__(
        self,
        project_root: str | Path,
        staging_root: str | Path,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.staging_root = Path(staging_root).resolve()

        if self.project_root == self.staging_root:
            raise ValueError(
                "Project root and staging root must be different."
            )

    def build_plan(self) -> DiffPlan:
        if not self.project_root.exists():
            raise FileNotFoundError(
                f"Project root does not exist: {self.project_root}"
            )

        if not self.project_root.is_dir():
            raise NotADirectoryError(
                f"Project root is not a directory: {self.project_root}"
            )

        if not self.staging_root.exists():
            raise FileNotFoundError(
                f"Staging root does not exist: {self.staging_root}"
            )

        if not self.staging_root.is_dir():
            raise NotADirectoryError(
                f"Staging root is not a directory: {self.staging_root}"
            )

        staged_files = sorted(
            path
            for path in self.staging_root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )

        file_diffs: list[FileDiff] = []

        for staged_path in staged_files:
            relative_path = staged_path.relative_to(
                self.staging_root
            )

            project_path = self._safe_project_path(relative_path)

            staged_hash = self._hash_file(staged_path)

            if not project_path.exists():
                file_diffs.append(
                    FileDiff(
                        relative_path=relative_path.as_posix(),
                        change_type=ChangeType.NEW,
                        staged_hash=staged_hash,
                        project_hash=None,
                    )
                )
                continue

            if not project_path.is_file():
                raise ValueError(
                    "Staged file conflicts with a non-file project path: "
                    f"{relative_path.as_posix()}"
                )

            project_hash = self._hash_file(project_path)

            change_type = (
                ChangeType.UNCHANGED
                if staged_hash == project_hash
                else ChangeType.MODIFIED
            )

            file_diffs.append(
                FileDiff(
                    relative_path=relative_path.as_posix(),
                    change_type=change_type,
                    staged_hash=staged_hash,
                    project_hash=project_hash,
                )
            )

        return DiffPlan(files=file_diffs)

    def format_plan(self, plan: DiffPlan) -> str:
        lines = [
            "ATLAS WORKSPACE DIFF",
            "====================",
        ]

        if not plan.files:
            lines.append("No staged files found.")
            return "\n".join(lines)

        symbols = {
            ChangeType.NEW: "+",
            ChangeType.MODIFIED: "*",
            ChangeType.UNCHANGED: "=",
        }

        for file_diff in plan.files:
            symbol = symbols[file_diff.change_type]
            label = file_diff.change_type.value.upper()

            lines.append(
                f"{symbol} {label:<9} {file_diff.relative_path}"
            )

        lines.extend(
            [
                "",
                f"New       : {len(plan.new_files)}",
                f"Modified  : {len(plan.modified_files)}",
                f"Unchanged : {len(plan.unchanged_files)}",
                f"Actionable: {len(plan.actionable_files)}",
            ]
        )

        return "\n".join(lines)

    def _safe_project_path(self, relative_path: Path) -> Path:
        destination = (
            self.project_root / relative_path
        ).resolve()

        try:
            destination.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(
                "Unsafe project destination rejected: "
                f"{relative_path.as_posix()}"
            ) from exc

        return destination

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as file_handle:
            for chunk in iter(
                lambda: file_handle.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()
