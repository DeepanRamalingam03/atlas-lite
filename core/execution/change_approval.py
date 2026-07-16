from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import unified_diff
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any

from core.execution.workspace import SafeWorkspace


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(slots=True, frozen=True)
class FileDiff:
    relative_path: str
    original_exists: bool
    diff: str


@dataclass(slots=True, frozen=True)
class ChangeSet:
    fingerprint: str
    files: tuple[FileDiff, ...]
    rendered_diff: str


@dataclass(slots=True, frozen=True)
class ApprovalRecord:
    fingerprint: str
    status: ApprovalStatus
    reason: str | None
    created_at: str
    decided_at: str | None


class ChangeDiffGenerator:
    """
    Generates unified diffs between project files and staged files.
    """

    def __init__(
        self,
        workspace: SafeWorkspace,
    ) -> None:
        self.workspace = workspace

    def generate(self) -> ChangeSet:
        staged_files = self.workspace.list_staged_files()

        if not staged_files:
            raise ValueError(
                "No staged files are available for diff generation."
            )

        file_diffs: list[FileDiff] = []
        rendered_sections: list[str] = []

        for relative_path in staged_files:
            project_path = (
                self.workspace.project_root
                / relative_path
            )

            staged_path = (
                self.workspace.staging_root
                / relative_path
            )

            original_exists = project_path.exists()

            original_text = (
                project_path.read_text(
                    encoding="utf-8"
                )
                if original_exists
                else ""
            )

            staged_text = staged_path.read_text(
                encoding="utf-8"
            )

            original_lines = original_text.splitlines(
                keepends=True
            )

            staged_lines = staged_text.splitlines(
                keepends=True
            )

            diff_lines = list(
                unified_diff(
                    original_lines,
                    staged_lines,
                    fromfile=(
                        f"a/{relative_path}"
                        if original_exists
                        else "/dev/null"
                    ),
                    tofile=f"b/{relative_path}",
                    lineterm="",
                )
            )

            diff_text = "\n".join(diff_lines)

            file_diff = FileDiff(
                relative_path=relative_path,
                original_exists=original_exists,
                diff=diff_text,
            )

            file_diffs.append(file_diff)

            rendered_sections.append(
                diff_text
                or (
                    f"--- a/{relative_path}\n"
                    f"+++ b/{relative_path}\n"
                    "No textual changes."
                )
            )

        rendered_diff = "\n\n".join(
            rendered_sections
        )

        fingerprint = hashlib.sha256(
            rendered_diff.encode("utf-8")
        ).hexdigest()

        return ChangeSet(
            fingerprint=fingerprint,
            files=tuple(file_diffs),
            rendered_diff=rendered_diff,
        )


class HumanApprovalGate:
    """
    JSON-backed approval gate for staged change sets.

    A change set must be approved using its exact fingerprint.
    Any staged modification changes the fingerprint and invalidates
    the previous approval.
    """

    def __init__(
        self,
        storage_path: str | Path = (
            ".atlas_data/change_approvals.json"
        ),
    ) -> None:
        self.storage_path = Path(storage_path)
        self._lock = Lock()

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self._write_data({})

    def request(
        self,
        change_set: ChangeSet,
    ) -> ApprovalRecord:
        record = ApprovalRecord(
            fingerprint=change_set.fingerprint,
            status=ApprovalStatus.PENDING,
            reason=None,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
            decided_at=None,
        )

        with self._lock:
            data = self._read_data()
            data[change_set.fingerprint] = (
                self._serialize(record)
            )
            self._write_data(data)

        return record

    def approve(
        self,
        fingerprint: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        return self._decide(
            fingerprint=fingerprint,
            status=ApprovalStatus.APPROVED,
            reason=reason,
        )

    def reject(
        self,
        fingerprint: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        return self._decide(
            fingerprint=fingerprint,
            status=ApprovalStatus.REJECTED,
            reason=reason,
        )

    def load(
        self,
        fingerprint: str,
    ) -> ApprovalRecord | None:
        cleaned_fingerprint = fingerprint.strip()

        if not cleaned_fingerprint:
            raise ValueError(
                "fingerprint cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            raw_record = data.get(
                cleaned_fingerprint
            )

        if raw_record is None:
            return None

        if not isinstance(raw_record, dict):
            raise RuntimeError(
                "Stored approval record is invalid."
            )

        return self._deserialize(raw_record)

    def require_approved(
        self,
        change_set: ChangeSet,
    ) -> ApprovalRecord:
        record = self.load(
            change_set.fingerprint
        )

        if record is None:
            raise PermissionError(
                "No human approval exists for this change set."
            )

        if record.status != ApprovalStatus.APPROVED:
            raise PermissionError(
                "The staged change set is not approved."
            )

        return record

    def _decide(
        self,
        fingerprint: str,
        status: ApprovalStatus,
        reason: str | None,
    ) -> ApprovalRecord:
        cleaned_fingerprint = fingerprint.strip()

        if not cleaned_fingerprint:
            raise ValueError(
                "fingerprint cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            raw_record = data.get(
                cleaned_fingerprint
            )

            if raw_record is None:
                raise KeyError(
                    "Approval request does not exist."
                )

            current_record = self._deserialize(
                raw_record
            )

            if (
                current_record.status
                != ApprovalStatus.PENDING
            ):
                raise RuntimeError(
                    "Approval request was already decided."
                )

            decided_record = ApprovalRecord(
                fingerprint=cleaned_fingerprint,
                status=status,
                reason=(
                    reason.strip()
                    if reason is not None
                    and reason.strip()
                    else None
                ),
                created_at=current_record.created_at,
                decided_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

            data[cleaned_fingerprint] = (
                self._serialize(decided_record)
            )

            self._write_data(data)

        return decided_record

    @staticmethod
    def _serialize(
        record: ApprovalRecord,
    ) -> dict[str, Any]:
        payload = asdict(record)
        payload["status"] = record.status.value
        return payload

    @staticmethod
    def _deserialize(
        payload: dict[str, Any],
    ) -> ApprovalRecord:
        try:
            return ApprovalRecord(
                fingerprint=str(
                    payload["fingerprint"]
                ),
                status=ApprovalStatus(
                    payload["status"]
                ),
                reason=(
                    str(payload["reason"])
                    if payload.get("reason")
                    is not None
                    else None
                ),
                created_at=str(
                    payload["created_at"]
                ),
                decided_at=(
                    str(payload["decided_at"])
                    if payload.get("decided_at")
                    is not None
                    else None
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                "Stored approval record contains invalid data."
            ) from exc

    def _read_data(
        self,
    ) -> dict[str, dict[str, Any]]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return {}

            parsed = json.loads(content)

            if not isinstance(parsed, dict):
                raise RuntimeError(
                    "Approval store must contain a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Approval store contains invalid JSON."
            ) from exc

    def _write_data(
        self,
        data: dict[str, dict[str, Any]],
    ) -> None:
        temporary_path = (
            self.storage_path.with_suffix(
                self.storage_path.suffix + ".tmp"
            )
        )

        temporary_path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.storage_path
        )
