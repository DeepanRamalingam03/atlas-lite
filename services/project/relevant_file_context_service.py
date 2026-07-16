from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.project.project_file_reader import (
    ProjectFileContent,
    ProjectFileReader,
)
from services.project.relevant_file_selector import (
    RelevantFile,
    RelevantFileSelector,
)


@dataclass(slots=True, frozen=True)
class RelevantFileContext:
    selected_files: tuple[RelevantFile, ...]
    file_contents: tuple[ProjectFileContent, ...]
    rendered_context: str


class RelevantFileContextService:
    """
    Selects likely relevant project files and safely reads their contents.

    The result is prompt-ready context containing:
    - selected file paths,
    - relevance scores and reasons,
    - actual UTF-8 file contents,
    - truncation information.

    Secret and excluded files remain blocked by ProjectFileReader.
    """

    def __init__(
        self,
        project_root: str | Path,
        selector: RelevantFileSelector | None = None,
        reader: ProjectFileReader | None = None,
        max_files: int = 8,
        max_total_characters: int = 80_000,
    ) -> None:
        if max_files < 1:
            raise ValueError(
                "max_files must be at least 1."
            )

        if max_total_characters < 1_000:
            raise ValueError(
                "max_total_characters must be at least 1000."
            )

        self.project_root = Path(project_root).resolve()

        self.selector = selector or RelevantFileSelector(
            max_selected_files=max_files,
        )

        self.reader = reader or ProjectFileReader(
            project_root=self.project_root,
        )

        self.max_files = max_files
        self.max_total_characters = max_total_characters

    def build(
        self,
        request: str,
    ) -> RelevantFileContext:
        cleaned_request = request.strip()

        if not cleaned_request:
            raise ValueError(
                "Request cannot be empty."
            )

        selected_files = self.selector.select(
            project_root=self.project_root,
            request=cleaned_request,
        )

        if not selected_files:
            return RelevantFileContext(
                selected_files=(),
                file_contents=(),
                rendered_context=(
                    "No relevant project files were selected "
                    "for this request."
                ),
            )

        selected_files = selected_files[: self.max_files]

        readable_files: list[RelevantFile] = []
        file_contents: list[ProjectFileContent] = []
        read_errors: list[str] = []

        for selected_file in selected_files:
            try:
                content = self.reader.read(
                    selected_file.path
                )
            except (
                FileNotFoundError,
                IsADirectoryError,
                PermissionError,
                ValueError,
                OSError,
            ) as exc:
                read_errors.append(
                    f"{selected_file.path}: {exc}"
                )
                continue

            readable_files.append(selected_file)
            file_contents.append(content)

        rendered = self._render(
            request=cleaned_request,
            selected_files=readable_files,
            file_contents=file_contents,
            read_errors=read_errors,
        )

        return RelevantFileContext(
            selected_files=tuple(readable_files),
            file_contents=tuple(file_contents),
            rendered_context=rendered,
        )

    def _render(
        self,
        request: str,
        selected_files: list[RelevantFile],
        file_contents: list[ProjectFileContent],
        read_errors: list[str],
    ) -> str:
        sections: list[str] = [
            "RELEVANT PROJECT FILE CONTEXT",
            "=============================",
            f"Request: {request}",
        ]

        if not selected_files:
            sections.append(
                "\nNo selected project files could be read."
            )

        for selected_file, file_content in zip(
            selected_files,
            file_contents,
            strict=True,
        ):
            reasons = ", ".join(
                selected_file.reasons
            ) or "No scoring reason recorded."

            metadata = (
                f"FILE: {file_content.path}\n"
                f"SCORE: {selected_file.score}\n"
                f"REASONS: {reasons}\n"
                f"SIZE_BYTES: {file_content.size_bytes}\n"
                f"TRUNCATED: {file_content.truncated}"
            )

            sections.append(
                f"\n{metadata}\n"
                "CONTENT\n"
                "-------\n"
                f"{file_content.content}"
            )

        if read_errors:
            sections.append(
                "\nFILES NOT READ\n"
                "--------------\n"
                + "\n".join(
                    f"- {error}"
                    for error in read_errors
                )
            )

        rendered = "\n".join(sections)

        if len(rendered) <= self.max_total_characters:
            return rendered

        notice = (
            "\n\nRELEVANT FILE CONTEXT TRUNCATED\n"
            "===============================\n"
            "The selected file context exceeded the configured "
            "character limit."
        )

        available = (
            self.max_total_characters
            - len(notice)
        )

        return (
            rendered[:available].rstrip()
            + notice
        )
