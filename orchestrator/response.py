from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionResponse:
    content: str
    provider: str
    success: bool = True

