from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CodeValidationResult:
    valid: bool
    code: str | None
    error: str | None


class PythonCodeValidator:
    """
    Extracts and syntax-validates Python code returned by an AI provider.
    """

    PYTHON_BLOCK_PATTERN = re.compile(
        r"```(?:python|py)?\s*(.*?)```",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def validate_response(
        self,
        response: str,
    ) -> CodeValidationResult:
        cleaned_response = response.strip()

        if not cleaned_response:
            return CodeValidationResult(
                valid=False,
                code=None,
                error="AI provider returned an empty response.",
            )

        code = self._extract_python_code(cleaned_response)

        if code is None:
            return CodeValidationResult(
                valid=True,
                code=None,
                error=None,
            )

        try:
            ast.parse(code)
        except SyntaxError as exc:
            location = (
                f"line {exc.lineno}, column {exc.offset}"
                if exc.lineno is not None
                else "unknown location"
            )

            return CodeValidationResult(
                valid=False,
                code=code,
                error=(
                    f"Python syntax error at {location}: "
                    f"{exc.msg}"
                ),
            )

        return CodeValidationResult(
            valid=True,
            code=code,
            error=None,
        )

    def _extract_python_code(
        self,
        response: str,
    ) -> str | None:
        matches = self.PYTHON_BLOCK_PATTERN.findall(response)

        if not matches:
            return None

        return "\n\n".join(
            match.strip()
            for match in matches
            if match.strip()
        )
