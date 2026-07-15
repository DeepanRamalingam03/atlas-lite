from __future__ import annotations

from dataclasses import dataclass

from managers.base_manager import BaseManager
from workers.base_worker import BaseWorker


@dataclass(slots=True)
class CycleResult:
    goal: str
    worker_prompt: str
    worker_output: str
    manager_review: str
    approved: bool
    iterations: int


class AICycleOrchestrator:
    """
    Runs the Atlas Lite Manager -> Worker -> Review iteration loop.
    """

    def __init__(
        self,
        manager: BaseManager,
        worker: BaseWorker,
        max_iterations: int = 3,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")

        self.manager = manager
        self.worker = worker
        self.max_iterations = max_iterations

    def execute(self, goal: str) -> CycleResult:
        cleaned_goal = goal.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        worker_prompt = self.manager.create_worker_prompt(cleaned_goal)
        worker_output = ""
        manager_review = ""

        for iteration in range(1, self.max_iterations + 1):
            worker_output = self.worker.execute(worker_prompt)

            manager_review = self.manager.review_worker_output(
                goal=cleaned_goal,
                worker_prompt=worker_prompt,
                worker_output=worker_output,
            )

            approved = self._is_approved(manager_review)

            if approved:
                return CycleResult(
                    goal=cleaned_goal,
                    worker_prompt=worker_prompt,
                    worker_output=worker_output,
                    manager_review=manager_review,
                    approved=True,
                    iterations=iteration,
                )

            fix_instruction = self._extract_fix_instruction(manager_review)

            worker_prompt = (
                f"{worker_prompt}\n\n"
                f"MANAGER REVIEW - ITERATION {iteration}:\n"
                f"{manager_review}\n\n"
                f"REQUIRED CORRECTION:\n"
                f"{fix_instruction}"
            )

        return CycleResult(
            goal=cleaned_goal,
            worker_prompt=worker_prompt,
            worker_output=worker_output,
            manager_review=manager_review,
            approved=False,
            iterations=self.max_iterations,
        )

    @staticmethod
    def _is_approved(review: str) -> bool:
        first_line = review.strip().splitlines()[0].strip().upper()
        return first_line == "DECISION: APPROVED"

    @staticmethod
    def _extract_fix_instruction(review: str) -> str:
        marker = "FIX_INSTRUCTION:"
        upper_review = review.upper()
        marker_index = upper_review.find(marker)

        if marker_index == -1:
            return review.strip()

        instruction = review[marker_index + len(marker):].strip()

        if not instruction or instruction.upper() == "NONE":
            return "Correct every issue identified in the manager review."

        return instruction
