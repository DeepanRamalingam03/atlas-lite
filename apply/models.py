from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ApplyResult:
    success: bool
    applied_paths: list[Path] = field(default_factory=list)
    rolled_back: bool = False
    error: str | None = None
