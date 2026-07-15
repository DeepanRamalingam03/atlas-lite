from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExecutionResponse:
    success: bool
    content: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)
