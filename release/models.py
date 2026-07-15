from __future__ import annotations

from dataclasses import dataclass

from apply.models import ApplyResult
from git_tools.models import GitPublishResult
from workspace.diff_engine import DiffPlan


@dataclass(slots=True)
class ReleaseResult:
    success: bool
    diff_plan: DiffPlan
    apply_result: ApplyResult | None = None
    git_result: GitPublishResult | None = None
    error: str | None = None
