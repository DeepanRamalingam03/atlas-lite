from __future__ import annotations

import json
from typing import Any

from core.file_change import FileChange


class WorkerOutputParser:
    """
    Parses a worker JSON response into validated FileChange objects.

    Expected worker output:

    {
      "summary": "Short description",
      "files": [
        {
          "path": "example.py",
          "content": "complete file content"
        }
      ]
    }
    """

    def parse(self, worker_output: str) -> tuple[str, list[FileChange]]:
        cleaned_output = worker_output.strip()

        if not cleaned_output:
            raise ValueError("Worker output cannot be empty.")

        json_text = self._extract_json(cleaned_output)

        try:
            payload: Any = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Worker output is not valid JSON: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ValueError("Worker output root must be a JSON object.")

        summary = payload.get("summary", "")
        files = payload.get("files")

        if not isinstance(summary, str):
            raise ValueError("'summary' must be a string.")

        if not isinstance(files, list):
            raise ValueError("'files' must be a list.")

        parsed_files: list[FileChange] = []

        for index, item in enumerate(files):
            if not isinstance(item, dict):
                raise ValueError(
                    f"File entry at index {index} must be an object."
                )

            path = item.get("path")
            content = item.get("content")

            if not isinstance(path, str):
                raise ValueError(
                    f"File entry at index {index} has an invalid path."
                )

            if not isinstance(content, str):
                raise ValueError(
                    f"File entry at index {index} has invalid content."
                )

            parsed_files.append(
                FileChange(
                    path=path,
                    content=content,
                )
            )

        if not parsed_files:
            raise ValueError("Worker output contains no file changes.")

        return summary.strip(), parsed_files

    @staticmethod
    def _extract_json(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()

            if len(lines) < 3:
                raise ValueError("Invalid fenced JSON response.")

            if lines[0].strip().lower() in {"```json", "```"}:
                if lines[-1].strip() != "```":
                    raise ValueError("JSON code fence is not closed.")

                return "\n".join(lines[1:-1]).strip()

        return text
