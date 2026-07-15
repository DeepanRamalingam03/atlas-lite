from __future__ import annotations

from abc import ABC, abstractmethod


class BaseClient(ABC):
    """Common interface implemented by every AI provider client."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate and return a plain-text response."""
        raise NotImplementedError
