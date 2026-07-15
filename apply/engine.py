from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from apply.models import ApplyResult
from workspace.diff_engine import ChangeType, DiffPlan, FileDiff


class TransactionalApplyEngine:
    """
    Applies staged NEW and MODIFIED files to the project transactionally.

    On failure:
    - Modified files are restored from backup.
    - Newly created files are removed.
    - Empty directories created during the transaction are removed safely.
    """

    PROTECTED_TOP_LEVEL_PATHS = {
        ".git",
        ".env",
        "venv",
        ".atlas_backups",
        ".atlas_staging",
    }

    def __init__(
        self,
        project_root: str | Path,
        staging_root: str | Path,
        backup_root: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.staging_root = Path(staging_root).resolve()

        self.backup_root = (
            Path(backup_root).resolve()
            if backup_root is not None
            else (self.project_root / ".atlas_backups").resolve()
        )

        if self.project_root == self.staging_root:
            raise ValueError(
                "Project root and staging root must be different."
            )

    def apply(self, plan: DiffPlan) -> ApplyResult:
        actionable = sorted(
            plan.actionable_files,
            key=lambda item: item.relative_path,
        )

        if not actionable:
            return ApplyResult(success=True)

        transaction_root = (
            self.backup_root / f"transaction-{uuid.uuid4().hex}"
        )

        backed_up_files: list[tuple[Path, Path]] = []
        created_files: list[Path] = []
        created_directories: list[Path] = []
        applied_paths: list[Path] = []

        try:
            transaction_root.mkdir(parents=True, exist_ok=False)

            for file_diff in actionable:
                self._validate_file_diff(file_diff)

                relative_path = Path(file_diff.relative_path)

                staged_path = self._safe_path(
                    root=self.staging_root,
                    relative_path=relative_path,
                    label="staging",
                )

                project_path = self._safe_path(
                    root=self.project_root,
                    relative_path=relative_path,
                    label="project",
                )

                if not staged_path.is_file():
                    raise FileNotFoundError(
                        f"Staged file does not exist: {relative_path}"
                    )

                if self._hash_file(staged_path) != file_diff.staged_hash:
                    raise RuntimeError(
                        "Staged file changed after diff creation: "
                        f"{relative_path}"
                    )

                if file_diff.change_type is ChangeType.MODIFIED:
                    if not project_path.is_file():
                        raise FileNotFoundError(
                            "Expected project file is missing: "
                            f"{relative_path}"
                        )

                    backup_path = self._safe_path(
                        root=transaction_root,
                        relative_path=relative_path,
                        label="backup",
                    )

                    self._create_parent_directories(
                        path=backup_path.parent,
                        created_directories=None,
                    )

                    shutil.copy2(project_path, backup_path)

                    backed_up_files.append(
                        (project_path, backup_path)
                    )

                elif file_diff.change_type is ChangeType.NEW:
                    if project_path.exists():
                        raise FileExistsError(
                            "Expected a new path, but it already exists: "
                            f"{relative_path}"
                        )

                    created_files.append(project_path)

                self._create_parent_directories(
                    path=project_path.parent,
                    created_directories=created_directories,
                )

                temporary_path = project_path.with_name(
                    f".{project_path.name}.atlas-tmp-{uuid.uuid4().hex}"
                )

                try:
                    shutil.copy2(staged_path, temporary_path)
                    temporary_path.replace(project_path)
                finally:
                    if temporary_path.exists():
                        temporary_path.unlink()

                if self._hash_file(project_path) != file_diff.staged_hash:
                    raise RuntimeError(
                        f"Applied file verification failed: {relative_path}"
                    )

                applied_paths.append(project_path)

        except Exception as exc:
            rollback_error = self._rollback(
                backed_up_files=backed_up_files,
                created_files=created_files,
                created_directories=created_directories,
            )

            self._remove_transaction(transaction_root)
            self._remove_empty_backup_root()

            error_message = f"{type(exc).__name__}: {exc}"

            if rollback_error:
                error_message += (
                    f" | Rollback error: {rollback_error}"
                )

            return ApplyResult(
                success=False,
                applied_paths=[],
                rolled_back=rollback_error is None,
                error=error_message,
            )

        self._remove_transaction(transaction_root)
        self._remove_empty_backup_root()

        return ApplyResult(
            success=True,
            applied_paths=applied_paths,
            rolled_back=False,
            error=None,
        )

    def _validate_file_diff(self, file_diff: FileDiff) -> None:
        if file_diff.change_type not in {
            ChangeType.NEW,
            ChangeType.MODIFIED,
        }:
            raise ValueError(
                "Apply engine received a non-actionable file: "
                f"{file_diff.relative_path}"
            )

        relative_path = Path(file_diff.relative_path)

        if relative_path.is_absolute():
            raise ValueError("Absolute paths are not allowed.")

        if ".." in relative_path.parts:
            raise ValueError(
                "Parent-directory traversal is not allowed."
            )

        if (
            relative_path.parts
            and relative_path.parts[0]
            in self.PROTECTED_TOP_LEVEL_PATHS
        ):
            raise PermissionError(
                "Protected project path cannot be modified: "
                f"{file_diff.relative_path}"
            )

    def _create_parent_directories(
        self,
        path: Path,
        created_directories: list[Path] | None,
    ) -> None:
        if path.exists():
            if not path.is_dir():
                raise NotADirectoryError(
                    f"Parent path is not a directory: {path}"
                )
            return

        missing: list[Path] = []
        current = path

        while not current.exists():
            missing.append(current)
            current = current.parent

        if not current.is_dir():
            raise NotADirectoryError(
                f"Parent path is not a directory: {current}"
            )

        for directory in reversed(missing):
            directory.mkdir()

            if created_directories is not None:
                created_directories.append(directory)

    @staticmethod
    def _safe_path(
        root: Path,
        relative_path: Path,
        label: str,
    ) -> Path:
        destination = (root / relative_path).resolve()

        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Unsafe {label} path rejected: {relative_path}"
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

    def _rollback(
        self,
        backed_up_files: list[tuple[Path, Path]],
        created_files: list[Path],
        created_directories: list[Path],
    ) -> str | None:
        try:
            for created_path in reversed(created_files):
                if created_path.is_file() or created_path.is_symlink():
                    created_path.unlink()

            for project_path, backup_path in reversed(
                backed_up_files
            ):
                project_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.copy2(backup_path, project_path)

            for directory in reversed(created_directories):
                if (
                    directory != self.project_root
                    and directory.exists()
                    and directory.is_dir()
                    and not any(directory.iterdir())
                ):
                    directory.rmdir()

            return None

        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _remove_transaction(transaction_root: Path) -> None:
        if transaction_root.exists():
            shutil.rmtree(transaction_root)

    def _remove_empty_backup_root(self) -> None:
        if (
            self.backup_root.exists()
            and self.backup_root.is_dir()
            and not any(self.backup_root.iterdir())
        ):
            self.backup_root.rmdir()
