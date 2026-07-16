from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Sequence


class AutonomyAction(str, Enum):
    READ = "read"
    PLAN = "plan"
    GENERATE_CHANGE = "generate_change"
    STAGE_CHANGE = "stage_change"
    VALIDATE = "validate"
    APPLY_CHANGE = "apply_change"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"

    MODIFY_CONSTITUTION = "modify_constitution"
    DESTRUCTIVE_OPERATION = "destructive_operation"
    PRODUCTION_DEPLOYMENT = "production_deployment"
    CREATE_PAID_RESOURCE = "create_paid_resource"
    ACCESS_SECRET = "access_secret"
    REQUEST_LOGIN = "request_login"
    ENABLE_LIVE_TRADING = "enable_live_trading"
    CHANGE_TRADING_RISK = "change_trading_risk"
    UNRECOVERABLE_BLOCKER = "unrecoverable_blocker"


class DecisionReason(str, Enum):
    ROUTINE_DEVELOPMENT = "routine_development"
    READ_ONLY_OPERATION = "read_only_operation"
    CONSTITUTION_CHANGE = "constitution_change"
    SECRET_REQUIRED = "secret_required"
    AUTHENTICATION_REQUIRED = "authentication_required"
    DESTRUCTIVE_OPERATION = "destructive_operation"
    PRODUCTION_OPERATION = "production_operation"
    PAID_RESOURCE = "paid_resource"
    LIVE_TRADING = "live_trading"
    TRADING_RISK_CHANGE = "trading_risk_change"
    UNRECOVERABLE_BLOCKER = "unrecoverable_blocker"
    PROTECTED_PATH = "protected_path"
    DISALLOWED_BRANCH = "disallowed_branch"
    FORCE_PUSH = "force_push"
    UNKNOWN_ACTION = "unknown_action"


@dataclass(frozen=True, slots=True)
class AutonomyRequest:
    action: AutonomyAction | str
    paths: Sequence[str] = ()
    branch: str | None = None
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    allowed: bool
    requires_human: bool
    reason: DecisionReason
    message: str

    @property
    def blocked(self) -> bool:
        return not self.allowed


class AutonomyPolicy:
    DEFAULT_DEVELOPMENT_BRANCHES = frozenset(
        {
            "main",
            "develop",
            "development",
            "atlas-dev",
            "atlas-development",
        }
    )

    ROUTINE_ACTIONS = frozenset(
        {
            AutonomyAction.PLAN,
            AutonomyAction.GENERATE_CHANGE,
            AutonomyAction.STAGE_CHANGE,
            AutonomyAction.VALIDATE,
            AutonomyAction.APPLY_CHANGE,
            AutonomyAction.GIT_COMMIT,
            AutonomyAction.GIT_PUSH,
        }
    )

    HUMAN_ACTIONS = {
        AutonomyAction.MODIFY_CONSTITUTION: (
            DecisionReason.CONSTITUTION_CHANGE,
            "Constitution changes require explicit human approval.",
        ),
        AutonomyAction.ACCESS_SECRET: (
            DecisionReason.SECRET_REQUIRED,
            "Secrets or missing credentials require human intervention.",
        ),
        AutonomyAction.REQUEST_LOGIN: (
            DecisionReason.AUTHENTICATION_REQUIRED,
            "Login, OTP, MFA or CAPTCHA requires human intervention.",
        ),
        AutonomyAction.DESTRUCTIVE_OPERATION: (
            DecisionReason.DESTRUCTIVE_OPERATION,
            "Destructive or irreversible operations require human approval.",
        ),
        AutonomyAction.PRODUCTION_DEPLOYMENT: (
            DecisionReason.PRODUCTION_OPERATION,
            "Production deployment requires human approval.",
        ),
        AutonomyAction.CREATE_PAID_RESOURCE: (
            DecisionReason.PAID_RESOURCE,
            "Paid resource creation requires human approval.",
        ),
        AutonomyAction.ENABLE_LIVE_TRADING: (
            DecisionReason.LIVE_TRADING,
            "Live trading cannot be enabled autonomously.",
        ),
        AutonomyAction.CHANGE_TRADING_RISK: (
            DecisionReason.TRADING_RISK_CHANGE,
            "Trading risk-limit changes require human approval.",
        ),
        AutonomyAction.UNRECOVERABLE_BLOCKER: (
            DecisionReason.UNRECOVERABLE_BLOCKER,
            "Unrecoverable blockers require human intervention.",
        ),
    }

    CONSTITUTION_ROOT = PurePosixPath(
        "atlas_core/constitution"
    )

    PROTECTED_PATH_PARTS = frozenset(
        {
            ".git",
            ".ssh",
            ".aws",
            "venv",
        }
    )

    SECRET_FILENAMES = frozenset(
        {
            ".env",
            ".env.local",
            ".env.production",
            ".env.prod",
            "credentials.json",
            "service-account.json",
            "service_account.json",
            "secrets.json",
            "id_rsa",
            "id_ed25519",
        }
    )

    SECRET_SUFFIXES = frozenset(
        {
            ".pem",
            ".key",
            ".p12",
            ".pfx",
        }
    )

    def __init__(
        self,
        development_branches: Iterable[str] | None = None,
    ) -> None:
        source_branches = (
            development_branches
            if development_branches is not None
            else self.DEFAULT_DEVELOPMENT_BRANCHES
        )

        normalized_branches = {
            branch.strip()
            for branch in source_branches
            if isinstance(branch, str)
            and branch.strip()
        }

        if not normalized_branches:
            raise ValueError(
                "At least one development branch is required."
            )

        self._development_branches = frozenset(
            normalized_branches
        )

    @property
    def development_branches(
        self,
    ) -> frozenset[str]:
        return self._development_branches

    def evaluate(
        self,
        request: AutonomyRequest,
    ) -> AutonomyDecision:
        action = self._normalize_action(
            request.action
        )

        if action is None:
            return AutonomyDecision(
                allowed=False,
                requires_human=True,
                reason=DecisionReason.UNKNOWN_ACTION,
                message=(
                    "Unknown autonomy action: "
                    f"{request.action!r}"
                ),
            )

        human_rule = self.HUMAN_ACTIONS.get(
            action
        )

        if human_rule is not None:
            reason, message = human_rule

            return AutonomyDecision(
                allowed=False,
                requires_human=True,
                reason=reason,
                message=message,
            )

        path_decision = self._evaluate_paths(
            request.paths
        )

        if path_decision is not None:
            return path_decision

        metadata = request.metadata or {}

        if self._is_truthy(
            metadata.get("force_push")
        ):
            return AutonomyDecision(
                allowed=False,
                requires_human=True,
                reason=DecisionReason.FORCE_PUSH,
                message="Force push is prohibited.",
            )

        if action is AutonomyAction.GIT_PUSH:
            branch = (
                request.branch or ""
            ).strip()

            if (
                not branch
                or branch
                not in self._development_branches
            ):
                return AutonomyDecision(
                    allowed=False,
                    requires_human=True,
                    reason=(
                        DecisionReason.DISALLOWED_BRANCH
                    ),
                    message=(
                        "Automatic push is allowed only "
                        "to approved development branches: "
                        f"{sorted(self._development_branches)}"
                    ),
                )

        if action is AutonomyAction.READ:
            return AutonomyDecision(
                allowed=True,
                requires_human=False,
                reason=(
                    DecisionReason.READ_ONLY_OPERATION
                ),
                message=(
                    "Read-only operation is autonomous."
                ),
            )

        if action in self.ROUTINE_ACTIONS:
            return AutonomyDecision(
                allowed=True,
                requires_human=False,
                reason=(
                    DecisionReason.ROUTINE_DEVELOPMENT
                ),
                message=(
                    "Routine source-code and test work "
                    "is approved for autonomous execution."
                ),
            )

        return AutonomyDecision(
            allowed=False,
            requires_human=True,
            reason=DecisionReason.UNKNOWN_ACTION,
            message=(
                "No autonomy rule exists for action "
                f"{action.value!r}."
            ),
        )

    def require_allowed(
        self,
        request: AutonomyRequest,
    ) -> AutonomyDecision:
        decision = self.evaluate(request)

        if decision.blocked:
            raise PermissionError(
                decision.message
            )

        return decision

    def _evaluate_paths(
        self,
        paths: Sequence[str],
    ) -> AutonomyDecision | None:
        for raw_path in paths:
            path = self._normalize_path(
                raw_path
            )

            if path is None:
                return AutonomyDecision(
                    allowed=False,
                    requires_human=True,
                    reason=(
                        DecisionReason.PROTECTED_PATH
                    ),
                    message=(
                        "Unsafe or invalid path blocked: "
                        f"{raw_path!r}"
                    ),
                )

            if (
                path == self.CONSTITUTION_ROOT
                or self.CONSTITUTION_ROOT
                in path.parents
            ):
                return AutonomyDecision(
                    allowed=False,
                    requires_human=True,
                    reason=(
                        DecisionReason.CONSTITUTION_CHANGE
                    ),
                    message=(
                        "Constitution files cannot be "
                        "modified autonomously."
                    ),
                )

            if any(
                part in self.PROTECTED_PATH_PARTS
                for part in path.parts
            ):
                return AutonomyDecision(
                    allowed=False,
                    requires_human=True,
                    reason=(
                        DecisionReason.PROTECTED_PATH
                    ),
                    message=(
                        "Protected path blocked: "
                        f"{raw_path!r}"
                    ),
                )

            filename = path.name.lower()

            if (
                filename
                in self.SECRET_FILENAMES
                or filename.startswith(".env")
                or path.suffix.lower()
                in self.SECRET_SUFFIXES
            ):
                return AutonomyDecision(
                    allowed=False,
                    requires_human=True,
                    reason=(
                        DecisionReason.SECRET_REQUIRED
                    ),
                    message=(
                        "Secret-bearing file blocked: "
                        f"{raw_path!r}"
                    ),
                )

        return None

    @staticmethod
    def _normalize_action(
        action: AutonomyAction | str,
    ) -> AutonomyAction | None:
        if isinstance(
            action,
            AutonomyAction,
        ):
            return action

        if not isinstance(action, str):
            return None

        try:
            return AutonomyAction(
                action.strip().lower()
            )
        except ValueError:
            return None

    @staticmethod
    def _normalize_path(
        raw_path: str,
    ) -> PurePosixPath | None:
        if not isinstance(raw_path, str):
            return None

        cleaned_path = (
            raw_path.strip()
            .replace("\\", "/")
        )

        if not cleaned_path:
            return None

        path = PurePosixPath(
            cleaned_path
        )

        if (
            path.is_absolute()
            or ".." in path.parts
        ):
            return None

        return path

    @staticmethod
    def _is_truthy(
        value: object,
    ) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return (
                value.strip().lower()
                in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            )

        return bool(value)
