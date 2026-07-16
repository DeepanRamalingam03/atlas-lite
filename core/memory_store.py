from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(slots=True, frozen=True)
class MemoryTurn:
    role: str
    content: str


class PersistentMemoryStore:
    """
    Thread-safe JSON-backed conversation memory.

    This stores only Atlas conversation turns.
    API keys, Discord tokens, and other secrets must never be stored here.
    """

    def __init__(
        self,
        storage_path: str | Path,
        max_turns_per_user: int = 12,
    ) -> None:
        if max_turns_per_user < 2:
            raise ValueError(
                "max_turns_per_user must be at least 2."
            )

        self.storage_path = Path(storage_path)
        self.max_turns_per_user = max_turns_per_user
        self._lock = Lock()

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self._write_data({})

    def get_history(
        self,
        user_id: int,
    ) -> list[MemoryTurn]:
        with self._lock:
            data = self._read_data()
            raw_turns = data.get(str(user_id), [])

        turns: list[MemoryTurn] = []

        for item in raw_turns:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if isinstance(role, str) and isinstance(content, str):
                turns.append(
                    MemoryTurn(
                        role=role,
                        content=content,
                    )
                )

        return turns

    def append_exchange(
        self,
        user_id: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        cleaned_user_message = user_message.strip()
        cleaned_assistant_message = assistant_message.strip()

        if not cleaned_user_message:
            raise ValueError("User message cannot be empty.")

        if not cleaned_assistant_message:
            raise ValueError(
                "Assistant message cannot be empty."
            )

        with self._lock:
            data = self._read_data()
            user_key = str(user_id)

            raw_turns = data.setdefault(user_key, [])

            raw_turns.extend(
                [
                    asdict(
                        MemoryTurn(
                            role="USER",
                            content=cleaned_user_message,
                        )
                    ),
                    asdict(
                        MemoryTurn(
                            role="ATLAS",
                            content=cleaned_assistant_message,
                        )
                    ),
                ]
            )

            data[user_key] = raw_turns[
                -self.max_turns_per_user:
            ]

            self._write_data(data)

    def clear(self, user_id: int) -> None:
        with self._lock:
            data = self._read_data()
            data.pop(str(user_id), None)
            self._write_data(data)

    def history_size(self, user_id: int) -> int:
        return len(self.get_history(user_id))

    def _read_data(self) -> dict[str, list[dict[str, Any]]]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8"
            ).strip()

            if not content:
                return {}

            parsed = json.loads(content)

            if not isinstance(parsed, dict):
                raise ValueError(
                    "Memory storage root must be a JSON object."
                )

            return parsed

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Atlas memory file is invalid JSON: "
                f"{self.storage_path}"
            ) from exc

    def _write_data(
        self,
        data: dict[str, list[dict[str, Any]]],
    ) -> None:
        temporary_path = self.storage_path.with_suffix(
            self.storage_path.suffix + ".tmp"
        )

        temporary_path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(self.storage_path)
