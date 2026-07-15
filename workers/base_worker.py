from __future__ import annotations

from abc import ABC, abstractmethod


class BaseWorker(ABC):
    """Common interface for Atlas Lite implementation workers."""

    @abstractmethod
    def execute(self, instruction: str) -> str:
        """Execute a manager instruction and return the result."""
        raise NotImplementedError
