from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class FileOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"


@dataclass(slots=True, frozen=True)
class ProposedFileChange:
    path: str
    operation: FileOperation
    content: str


@dataclass(slots=True, frozen=True)
class ChangeProposal:
    summary: str
    changes: tuple[ProposedFileChange, ...]
    test_commands: tuple[tuple[str, ...], ...]


class ChangeProposalError(ValueError):
    """Raised when worker change output is invalid or unsafe."""


class ChangeProposalParser:
    """
    Parses and validates structured worker file-change proposals.

    Accepted worker response:

    {
      "summary": "What was changed",
      "changes": [
        {
          "path": "core/example.py",
          "operation": "update",
          "content": "complete file content"
        }
      ],
      "test_commands": [
        ["python", "test_example.py"]
      ]
    }

    JSON may be raw or inside a fenced ```json block.
    """

    EXCLUDED_DIRECTORIES = {
        ".git",
        ".github",
        ".atlas_data",
        ".atlas_staging",
        ".atlas_validation",
        ".atlas_apply_backup",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
    }

    PROTECTED_FILES = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_ed25519",
    }

    BLOCKED_SUFFIXES = {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".crt",
        ".cer",
        ".der",
        ".sqlite",
        ".db",
        ".pyc",
    }

    ALLOWED_TEST_EXECUTABLES = {
        "python",
        "python3",
        "pytest",
    }

    BLOCKED_COMMAND_ARGUMENTS = {
        "-c",
        "--eval",
    }

    def __init__(
        self,
        max_files: int = 20,
        max_file_characters: int = 500_000,
        max_total_characters: int = 2_000_000,
        max_test_commands: int = 20,
    ) -> None:
        if max_files < 1:
            raise ValueError("max_files must be at least 1.")

        if max_file_characters < 1_000:
            raise ValueError(
                "max_file_characters must be at least 1000."
            )

        if max_total_characters < max_file_characters:
            raise ValueError(
                "max_total_characters cannot be smaller "
                "than max_file_characters."
            )

        if max_test_commands < 0:
            raise ValueError(
                "max_test_commands cannot be negative."
            )

        self.max_files = max_files
        self.max_file_characters = max_file_characters
        self.max_total_characters = max_total_characters
        self.max_test_commands = max_test_commands

    def parse(
        self,
        worker_output: str,
    ) -> ChangeProposal:
        cleaned_output = worker_output.strip()

        if not cleaned_output:
            raise ChangeProposalError(
                "Worker change proposal is empty."
            )

        json_text = self._extract_json(cleaned_output)

        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ChangeProposalError(
                "Worker change proposal contains invalid JSON: "
                f"{exc.msg} at line {exc.lineno}, "
                f"column {exc.colno}."
            ) from exc

        if not isinstance(payload, dict):
            raise ChangeProposalError(
                "Worker change proposal root must be a JSON object."
            )

        summary = payload.get("summary")
        raw_changes = payload.get("changes")
        raw_test_commands = payload.get(
            "test_commands",
            [],
        )

        if not isinstance(summary, str) or not summary.strip():
            raise ChangeProposalError(
                "Change proposal summary must be a non-empty string."
            )

        if not isinstance(raw_changes, list):
            raise ChangeProposalError(
                "Change proposal changes must be a list."
            )

        if not raw_changes:
            raise ChangeProposalError(
                "Change proposal must contain at least one file change."
            )

        if len(raw_changes) > self.max_files:
            raise ChangeProposalError(
                f"Change proposal exceeds the {self.max_files}-file limit."
            )

        changes = self._parse_changes(raw_changes)

        test_commands = self._parse_test_commands(
            raw_test_commands
        )

        return ChangeProposal(
            summary=summary.strip(),
            changes=tuple(changes),
            test_commands=tuple(test_commands),
        )

    def render_worker_contract(self) -> str:
        return (
            "Return only one JSON object using this exact structure:\n"
            "{\n"
            '  "summary": "short implementation summary",\n'
            '  "changes": [\n'
            "    {\n"
            '      "path": "project/relative/path.py",\n'
            '      "operation": "create or update",\n'
            '      "content": "complete final file content"\n'
            "    }\n"
            "  ],\n"
            '  "test_commands": [\n'
            '    ["python", "test_file.py"]\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Return complete file content, not patches or fragments.\n"
            "- Use only project-relative paths.\n"
            "- Never include secrets, credentials, .env files, or keys.\n"
            "- Do not include shell operators or inline executable code.\n"
            "- Use an empty test_commands list when no test is applicable."
        )

    def _parse_changes(
        self,
        raw_changes: list[Any],
    ) -> list[ProposedFileChange]:
        changes: list[ProposedFileChange] = []
        seen_paths: set[str] = set()
        total_characters = 0

        for index, raw_change in enumerate(
            raw_changes,
            start=1,
        ):
            if not isinstance(raw_change, dict):
                raise ChangeProposalError(
                    f"File change {index} must be a JSON object."
                )

            raw_path = raw_change.get("path")
            raw_operation = raw_change.get("operation")
            raw_content = raw_change.get("content")

            if not isinstance(raw_path, str):
                raise ChangeProposalError(
                    f"File change {index} path must be a string."
                )

            normalized_path = self._validate_path(
                raw_path
            )

            if normalized_path in seen_paths:
                raise ChangeProposalError(
                    f"Duplicate file change path: {normalized_path}"
                )

            seen_paths.add(normalized_path)

            try:
                operation = FileOperation(
                    str(raw_operation).strip().lower()
                )
            except ValueError as exc:
                raise ChangeProposalError(
                    f"Invalid operation for {normalized_path}: "
                    f"{raw_operation!r}"
                ) from exc

            if not isinstance(raw_content, str):
                raise ChangeProposalError(
                    f"Content for {normalized_path} must be a string."
                )

            if len(raw_content) > self.max_file_characters:
                raise ChangeProposalError(
                    f"Content for {normalized_path} exceeds "
                    f"{self.max_file_characters} characters."
                )

            total_characters += len(raw_content)

            if total_characters > self.max_total_characters:
                raise ChangeProposalError(
                    "Combined file content exceeds the configured limit."
                )

            changes.append(
                ProposedFileChange(
                    path=normalized_path,
                    operation=operation,
                    content=raw_content,
                )
            )

        return changes

    def _parse_test_commands(
        self,
        raw_commands: Any,
    ) -> list[tuple[str, ...]]:
        if not isinstance(raw_commands, list):
            raise ChangeProposalError(
                "test_commands must be a list."
            )

        if len(raw_commands) > self.max_test_commands:
            raise ChangeProposalError(
                "Too many test commands were proposed."
            )

        parsed_commands: list[tuple[str, ...]] = []

        for index, raw_command in enumerate(
            raw_commands,
            start=1,
        ):
            if not isinstance(raw_command, list) or not raw_command:
                raise ChangeProposalError(
                    f"Test command {index} must be a non-empty list."
                )

            if not all(
                isinstance(argument, str)
                and argument.strip()
                for argument in raw_command
            ):
                raise ChangeProposalError(
                    f"Test command {index} contains an invalid argument."
                )

            command = tuple(
                argument.strip()
                for argument in raw_command
            )

            executable = Path(
                command[0]
            ).name.lower()

            if executable.endswith(".exe"):
                executable = executable[:-4]

            if executable not in self.ALLOWED_TEST_EXECUTABLES:
                raise ChangeProposalError(
                    f"Test command is not approved: {command[0]}"
                )

            if any(
                argument in self.BLOCKED_COMMAND_ARGUMENTS
                for argument in command[1:]
            ):
                raise ChangeProposalError(
                    "Inline code execution is blocked in test commands."
                )

            if any(
                self._contains_shell_operator(argument)
                for argument in command
            ):
                raise ChangeProposalError(
                    "Shell operators are blocked in test commands."
                )

            parsed_commands.append(command)

        return parsed_commands

    def _validate_path(
        self,
        raw_path: str,
    ) -> str:
        cleaned_path = raw_path.strip().replace(
            "\\",
            "/",
        )

        if not cleaned_path:
            raise ChangeProposalError(
                "File change path cannot be empty."
            )

        path = Path(cleaned_path)

        if path.is_absolute():
            raise ChangeProposalError(
                "Absolute file paths are not allowed."
            )

        if ".." in path.parts:
            raise ChangeProposalError(
                "File paths cannot escape the project root."
            )

        normalized_parts = tuple(
            part
            for part in path.parts
            if part not in {"", "."}
        )

        if not normalized_parts:
            raise ChangeProposalError(
                "File change path is invalid."
            )

        if any(
            part in self.EXCLUDED_DIRECTORIES
            for part in normalized_parts
        ):
            raise ChangeProposalError(
                f"Protected directory is blocked: {cleaned_path}"
            )

        filename = normalized_parts[-1]

        if filename in self.PROTECTED_FILES:
            raise ChangeProposalError(
                f"Protected file is blocked: {cleaned_path}"
            )

        if filename.startswith(".env."):
            raise ChangeProposalError(
                f"Environment secret file is blocked: {cleaned_path}"
            )

        suffix = Path(filename).suffix.lower()

        if suffix in self.BLOCKED_SUFFIXES:
            raise ChangeProposalError(
                f"Sensitive or binary file type is blocked: "
                f"{cleaned_path}"
            )

        return Path(
            *normalized_parts
        ).as_posix()

    @staticmethod
    def _extract_json(
        text: str,
    ) -> str:
        fenced_match = re.search(
            r"```(?:json)?\s*(\{.*\})\s*```",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if fenced_match:
            return fenced_match.group(1).strip()

        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if (
            first_brace == -1
            or last_brace == -1
            or last_brace < first_brace
        ):
            raise ChangeProposalError(
                "Worker response does not contain a JSON object."
            )

        return text[
            first_brace : last_brace + 1
        ].strip()

    @staticmethod
    def _contains_shell_operator(
        value: str,
    ) -> bool:
        return any(
            operator in value
            for operator in (
                "&&",
                "||",
                ";",
                "|",
                ">",
                "<",
                "`",
                "$(",
            )
        )
