from __future__ import annotations

from core.orchestration.directive_importer import (
    DirectiveImportResult,
    RoadmapDirectiveImporter,
)
from core.orchestration.runtime_service import (
    ContinuousRuntimeService,
    RuntimeCycleResult,
)


class DirectiveAwareRuntimeService(
    ContinuousRuntimeService
):
    """
    Imports architect directives before every runtime cycle.
    """

    def __init__(
        self,
        *args,
        directive_importer: RoadmapDirectiveImporter,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.directive_importer = (
            directive_importer
        )
        self.last_import_result: (
            DirectiveImportResult | None
        ) = None

    def run_once(self) -> RuntimeCycleResult:
        self.last_import_result = (
            self.directive_importer.import_pending()
        )

        return super().run_once()
