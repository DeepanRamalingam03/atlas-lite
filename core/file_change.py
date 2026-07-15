from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FileChange:
    path: str
    content: str

    def __post_init__(self) -> None:
        self.path = self.path.strip()

        if not self.path:
            raise ValueError("File path cannot be empty.")

        if self.path.startswith(("/", "\\")):
            raise ValueError("Absolute file paths are not allowed.")

        if ".." in self.path.split("/"):
            raise ValueError("Parent-directory traversal is not allowed.")
