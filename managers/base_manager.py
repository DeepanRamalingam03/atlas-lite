from __future__ import annotations

from abc import ABC, abstractmethod


class BaseManager(ABC):
    """
    Common interface for every Atlas Lite manager implementation.

    A manager is responsible for:
    - analysing the high-level goal
    - creating worker instructions
    - reviewing worker output
    - deciding whether the result is approved
    """

    @abstractmethod
    def create_worker_prompt(self, goal: str) -> str:
        """Create a strict implementation prompt for the worker."""
        raise NotImplementedError

    @abstractmethod
    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        """Review worker output and return the manager's decision."""
        raise NotImplementedError
