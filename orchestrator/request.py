from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionRequest:
    prompt: str
    context: str = ""
    provider: str = "gemini"
