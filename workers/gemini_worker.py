from __future__ import annotations

from clients.base_client import BaseClient
from workers.base_worker import BaseWorker


WORKER_SYSTEM_PROMPT = """
You are the Atlas Lite coding worker.

Rules:
- Perform implementation work only.
- Follow the manager instruction exactly.
- Do not redesign the architecture.
- Do not introduce unrelated files or features.
- When changing a file, return its complete content.
- Do not claim that code was tested unless test output was provided.
- Keep explanations minimal.
""".strip()


class GeminiWorker(BaseWorker):
    """Coding worker backed by a configured Gemini client."""

    def __init__(self, client: BaseClient) -> None:
        self.client = client

    def execute(self, instruction: str) -> str:
        cleaned_instruction = instruction.strip()

        if not cleaned_instruction:
            raise ValueError("Worker instruction cannot be empty.")

        prompt = (
            f"{WORKER_SYSTEM_PROMPT}\n\n"
            f"MANAGER INSTRUCTION:\n{cleaned_instruction}"
        )

        response = self.client.generate(prompt).strip()

        if not response:
            raise RuntimeError("Worker returned an empty response.")

        return response
