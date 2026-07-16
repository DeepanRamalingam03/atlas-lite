from __future__ import annotations

from pathlib import Path

from services.constitution_loader import ConstitutionLoader
from services.project.project_indexer import ProjectIndexer
from services.project.project_scanner import ProjectScanner


class ProjectContextBuilder:
    """
    Builds repository context for Atlas AI prompts.

    The context contains:
    - Atlas Constitution
    - Repository file structure
    - Python imports, classes, functions, and methods

    Project source code is inspected statically and never executed.
    """

    def __init__(
        self,
        constitution_loader: ConstitutionLoader | None = None,
        scanner: ProjectScanner | None = None,
        indexer: ProjectIndexer | None = None,
        max_context_characters: int = 120_000,
    ) -> None:
        if max_context_characters < 1_000:
            raise ValueError(
                "max_context_characters must be at least 1000."
            )

        self.constitution_loader = (
            constitution_loader or ConstitutionLoader()
        )
        self.scanner = scanner or ProjectScanner()
        self.indexer = indexer or ProjectIndexer()
        self.max_context_characters = max_context_characters

    def build(
        self,
        project_root: str | Path,
    ) -> str:
        root = Path(project_root).resolve()

        if not root.exists():
            raise FileNotFoundError(
                f"Project root does not exist: {root}"
            )

        if not root.is_dir():
            raise NotADirectoryError(
                f"Project root is not a directory: {root}"
            )

        constitution = (
            self.constitution_loader.load_all().strip()
        )

        if not constitution:
            raise RuntimeError(
                "Atlas Constitution is empty or unavailable."
            )

        structure = self.scanner.scan(root).strip()

        if not structure:
            raise RuntimeError(
                "Project structure is empty or unavailable."
            )

        indexes = self.indexer.index_project(root)
        rendered_index = self.indexer.render(indexes).strip()

        if not rendered_index:
            rendered_index = (
                "No Python source files were available for indexing."
            )

        context = "\n\n".join(
            [
                "ATLAS CONSTITUTION",
                "==================",
                constitution,
                "PROJECT FILE STRUCTURE",
                "======================",
                structure,
                "PYTHON PROJECT INDEX",
                "====================",
                rendered_index,
            ]
        )

        if len(context) <= self.max_context_characters:
            return context

        truncation_notice = (
            "\n\nPROJECT CONTEXT TRUNCATED\n"
            "=========================\n"
            "The context exceeded the configured character limit. "
            "Only the beginning was included."
        )

        available_length = (
            self.max_context_characters
            - len(truncation_notice)
        )

        return (
            context[:available_length].rstrip()
            + truncation_notice
        )
