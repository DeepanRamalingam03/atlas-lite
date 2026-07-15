from __future__ import annotations

from clients.base_client import BaseClient
from managers.base_manager import BaseManager


MANAGER_SYSTEM_PROMPT = """
You are the Atlas Lite Manager.

Your role:
- Act as the lead architect and final reviewer.
- Analyse the user's goal.
- Break the goal into a precise implementation task.
- Preserve the approved architecture.
- Give the worker exact instructions.
- Never allow the worker to redesign the architecture without permission.
- Review the worker's response strictly.
- Approve only when the implementation fully satisfies the task.
""".strip()


WORKER_PROMPT_TEMPLATE = """
{manager_role}

HIGH-LEVEL GOAL:
{goal}

Create a precise implementation instruction for a coding worker.

Rules for the worker instruction:
- The worker must perform coding work only.
- The worker must not redesign the architecture.
- The worker must not suggest unrelated alternatives.
- The worker must return complete files when modifications are required.
- The worker must follow the requested folder structure.
- The worker must include tests when the task requires them.

Return only the final worker instruction.
""".strip()


REVIEW_PROMPT_TEMPLATE = """
{manager_role}

HIGH-LEVEL GOAL:
{goal}

WORKER INSTRUCTION:
{worker_prompt}

WORKER OUTPUT:
{worker_output}

Review the worker output carefully.

Return exactly this structure:

DECISION: APPROVED or REJECTED

REASON:
A concise explanation.

FIX_INSTRUCTION:
If rejected, provide the exact correction instruction for the worker.
If approved, write NONE.
""".strip()


class OpenAIManager(BaseManager):
    """
    Atlas Lite manager powered by a configured AI client.

    The client will later be the OpenAI API client, but this class depends
    only on BaseClient so the manager provider can be replaced cleanly.
    """

    def __init__(self, client: BaseClient) -> None:
        self.client = client

    def create_worker_prompt(self, goal: str) -> str:
        cleaned_goal = goal.strip()
        if not cleaned_goal:
            raise ValueError("Manager goal cannot be empty.")

        prompt = WORKER_PROMPT_TEMPLATE.format(
            manager_role=MANAGER_SYSTEM_PROMPT,
            goal=cleaned_goal,
        )

        response = self.client.generate(prompt).strip()
        if not response:
            raise RuntimeError("Manager returned an empty worker prompt.")

        return response

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        cleaned_goal = goal.strip()
        cleaned_worker_prompt = worker_prompt.strip()
        cleaned_worker_output = worker_output.strip()

        if not cleaned_goal:
            raise ValueError("Manager goal cannot be empty.")

        if not cleaned_worker_prompt:
            raise ValueError("Worker prompt cannot be empty.")

        if not cleaned_worker_output:
            raise ValueError("Worker output cannot be empty.")

        prompt = REVIEW_PROMPT_TEMPLATE.format(
            manager_role=MANAGER_SYSTEM_PROMPT,
            goal=cleaned_goal,
            worker_prompt=cleaned_worker_prompt,
            worker_output=cleaned_worker_output,
        )

        response = self.client.generate(prompt).strip()
        if not response:
            raise RuntimeError("Manager returned an empty review response.")

        return response
