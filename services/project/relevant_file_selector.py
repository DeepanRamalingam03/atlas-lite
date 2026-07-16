from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from services.project.project_indexer import (
    ProjectIndexer,
    PythonFileIndex,
)


@dataclass(slots=True, frozen=True)
class RelevantFile:
    path: str
    score: int
    reasons: tuple[str, ...]


class RelevantFileSelector:
    """
    Selects project files that are likely relevant to a user request.

    Selection is deterministic and based on:

    - file path names,
    - Python classes,
    - functions and methods,
    - imports,
    - exact phrases,
    - normalized request tokens.

    It does not read file contents and does not execute project code.
    """

    DEFAULT_STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "create",
        "do",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "modify",
        "of",
        "on",
        "or",
        "please",
        "the",
        "this",
        "to",
        "update",
        "use",
        "with",
    }

    def __init__(
        self,
        indexer: ProjectIndexer | None = None,
        max_selected_files: int = 8,
        minimum_score: int = 2,
    ) -> None:
        if max_selected_files < 1:
            raise ValueError(
                "max_selected_files must be at least 1."
            )

        if minimum_score < 1:
            raise ValueError(
                "minimum_score must be at least 1."
            )

        self.indexer = indexer or ProjectIndexer()
        self.max_selected_files = max_selected_files
        self.minimum_score = minimum_score

    def select(
        self,
        project_root: str | Path,
        request: str,
    ) -> list[RelevantFile]:
        cleaned_request = request.strip()

        if not cleaned_request:
            raise ValueError(
                "Request cannot be empty."
            )

        request_tokens = self._tokenize(
            cleaned_request
        )

        indexes = self.indexer.index_project(
            project_root
        )

        candidates = [
            self._score_file(
                file_index=file_index,
                request=cleaned_request,
                request_tokens=request_tokens,
            )
            for file_index in indexes
        ]

        relevant = [
            candidate
            for candidate in candidates
            if candidate.score >= self.minimum_score
        ]

        return sorted(
            relevant,
            key=lambda item: (
                -item.score,
                item.path,
            ),
        )[: self.max_selected_files]

    def render(
        self,
        selected_files: list[RelevantFile],
    ) -> str:
        if not selected_files:
            return "No relevant files were selected."

        sections: list[str] = []

        for selected_file in selected_files:
            reasons = ", ".join(
                selected_file.reasons
            )

            sections.append(
                f"- {selected_file.path}\n"
                f"  score: {selected_file.score}\n"
                f"  reasons: {reasons}"
            )

        return "\n".join(sections)

    def _score_file(
        self,
        file_index: PythonFileIndex,
        request: str,
        request_tokens: set[str],
    ) -> RelevantFile:
        score = 0
        reasons: list[str] = []

        normalized_path = self._normalize(
            file_index.path
        )

        path_tokens = self._tokenize(
            normalized_path
        )

        path_matches = sorted(
            request_tokens.intersection(path_tokens)
        )

        if path_matches:
            path_score = len(path_matches) * 5
            score += path_score
            reasons.append(
                "path match: "
                + ", ".join(path_matches)
            )

        filename_stem = Path(
            file_index.path
        ).stem

        normalized_filename = self._normalize(
            filename_stem
        )

        if (
            normalized_filename
            and normalized_filename in self._normalize(
                request
            )
        ):
            score += 8
            reasons.append(
                f"filename phrase: {filename_stem}"
            )

        for symbol in file_index.symbols:
            normalized_symbol = self._normalize(
                symbol.name
            )

            symbol_tokens = self._tokenize(
                normalized_symbol
            )

            symbol_matches = sorted(
                request_tokens.intersection(
                    symbol_tokens
                )
            )

            if symbol_matches:
                symbol_score = len(symbol_matches) * 4
                score += symbol_score
                reasons.append(
                    f"symbol {symbol.name}: "
                    + ", ".join(symbol_matches)
                )

            if (
                normalized_symbol
                and normalized_symbol
                in self._normalize(request)
            ):
                score += 10
                reasons.append(
                    f"exact symbol phrase: "
                    f"{symbol.name}"
                )

        for imported_module in file_index.imports:
            import_tokens = self._tokenize(
                imported_module
            )

            import_matches = sorted(
                request_tokens.intersection(
                    import_tokens
                )
            )

            if import_matches:
                import_score = len(import_matches) * 2
                score += import_score
                reasons.append(
                    "import match: "
                    + ", ".join(import_matches)
                )

        if file_index.error:
            score = 0
            reasons = [
                "file index contains an error"
            ]

        unique_reasons = tuple(
            dict.fromkeys(reasons)
        )

        return RelevantFile(
            path=file_index.path,
            score=score,
            reasons=unique_reasons,
        )

    def _tokenize(
        self,
        text: str,
    ) -> set[str]:
        normalized = self._normalize(text)

        tokens = {
            token
            for token in normalized.split()
            if len(token) >= 2
            and token not in self.DEFAULT_STOP_WORDS
        }

        expanded_tokens = set(tokens)

        for token in tokens:
            expanded_tokens.update(
                self._split_identifier(token)
            )

        return {
            token
            for token in expanded_tokens
            if len(token) >= 2
            and token not in self.DEFAULT_STOP_WORDS
        }

    @staticmethod
    def _normalize(text: str) -> str:
        camel_case_split = re.sub(
            r"([a-z0-9])([A-Z])",
            r"\1 \2",
            text,
        )

        return re.sub(
            r"[^a-zA-Z0-9]+",
            " ",
            camel_case_split,
        ).strip().lower()

    @staticmethod
    def _split_identifier(
        token: str,
    ) -> set[str]:
        return {
            part
            for part in re.split(
                r"[_\-.]+",
                token,
            )
            if part
        }
