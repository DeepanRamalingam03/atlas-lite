from __future__ import annotations

from clients.base_client import BaseClient
from workers.base_worker import BaseWorker


WORKER_SYSTEM_PROMPT = """
You are the Atlas Lite coding worker.

Follow the manager instruction exactly.

Rules:
- Perform implementation work only.
- Do not redesign the architecture.
- Do not create unrelated files or features.
- Return every modified or created file with its complete content.
- Never return partial patches or diff fragments.
- Do not claim that code was tested unless test output was provided.
- Return valid JSON only.
- Do not wrap the JSON in Markdown unless absolutely necessary.

Required response schema:

{
  "summary": "Short description of the implementation",
  "files": [
    {
      "path": "relative/path/to/file.py",
      "content": "complete file content"
    }
  ]
}
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
