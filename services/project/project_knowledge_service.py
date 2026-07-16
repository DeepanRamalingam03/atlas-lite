from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.project.project_context_builder import (
    ProjectContextBuilder,
)
from services.project.project_memory import (
    ProjectMemory,
    ProjectMemorySnapshot,
)


@dataclass(slots=True, frozen=True)
class ProjectKnowledgeResult:
    context: str
    fingerprint: str
    created_at: str
    changed: bool


class ProjectKnowledgeService:
    """
    Builds and persists Atlas repository knowledge.

    Responsibilities:
    - Build current project context.
    - Compare it with the stored project snapshot.
    - Save a new snapshot only when the context changed.
    - Return the authoritative context for AI prompts.
    """

    def __init__(
        self,
        context_builder: ProjectContextBuilder | None = None,
        memory: ProjectMemory | None = None,
    ) -> None:
        self.context_builder = (
            context_builder or ProjectContextBuilder()
        )
        self.memory = memory or ProjectMemory()

    def refresh(
        self,
        project_root: str | Path,
    ) -> ProjectKnowledgeResult:
        root = Path(project_root).resolve()

        context = self.context_builder.build(root).strip()

        if not context:
            raise RuntimeError(
                "Generated project knowledge is empty."
            )

        existing_snapshot = self.memory.load(root)

        if (
            existing_snapshot is not None
            and existing_snapshot.fingerprint
            == self.memory.fingerprint(context)
        ):
            return self._to_result(
                snapshot=existing_snapshot,
                changed=False,
            )

        saved_snapshot = self.memory.save(
            project_root=root,
            context=context,
        )

        return self._to_result(
            snapshot=saved_snapshot,
            changed=True,
        )

    def load(
        self,
        project_root: str | Path,
    ) -> ProjectKnowledgeResult | None:
        snapshot = self.memory.load(project_root)

        if snapshot is None:
            return None

        return self._to_result(
            snapshot=snapshot,
            changed=False,
        )

    def get_or_refresh(
        self,
        project_root: str | Path,
    ) -> ProjectKnowledgeResult:
        existing = self.load(project_root)

        if existing is not None:
            return existing

        return self.refresh(project_root)

    def clear(
        self,
        project_root: str | Path,
    ) -> None:
        self.memory.clear(project_root)

    @staticmethod
    def _to_result(
        snapshot: ProjectMemorySnapshot,
        changed: bool,
    ) -> ProjectKnowledgeResult:
        return ProjectKnowledgeResult(
            context=snapshot.context,
            fingerprint=snapshot.fingerprint,
            created_at=snapshot.created_at,
            changed=changed,
        )
