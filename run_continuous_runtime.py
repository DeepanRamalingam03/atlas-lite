from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from threading import Event

import config
from apply.engine import TransactionalApplyEngine
from clients.factory import ClientFactory
from core.orchestration.autonomy_policy import (
    AutonomyPolicy,
)
from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
)
from core.orchestration.directive_importer import (
    ArchitectDirectiveStore,
    RoadmapDirectiveImporter,
)
from core.orchestration.directive_runtime import (
    DirectiveAwareRuntimeService,
)
from core.orchestration.observability import (
    RuntimeAlertStore,
    RuntimeDiskCleaner,
    RuntimeHeartbeatStore,
    RuntimeObserver,
)
from core.orchestration.production_guard import (
    DiskPressureGuard,
    LockedReleaseCoordinator,
    ProductionPreflight,
    RepositoryOperationLock,
)
from core.orchestration.recovery_manager import (
    WorkflowRecoveryManager,
)
from core.orchestration.retry_policy import (
    RetryStateStore,
    RuntimeRetryPolicy,
)
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStore,
)
from core.orchestration.runtime_lock import (
    RuntimeProcessLock,
)
from core.orchestration.runtime_service import (
    RuntimeCycleResult,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)
from git_tools.engine import GitEngine
from managers.openai_manager import OpenAIManager
from orchestrator.pipeline import AtlasPipeline
from release.coordinator import ReleaseCoordinator
from services.prompt_builder import PromptBuilder
from services.review_parser import ReviewParser
from services.worker_output_parser import (
    WorkerOutputParser,
)
from testing.runner import StagingTestRunner
from utils.logger import setup_logger
from workers.gemini_worker import GeminiWorker
from workspace.diff_engine import WorkspaceDiffEngine
from workspace.writer import WorkspaceWriter


PROJECT_ROOT = Path(__file__).resolve().parent
STAGING_ROOT = PROJECT_ROOT / ".atlas_staging"
DATA_ROOT = PROJECT_ROOT / ".atlas_data"
BACKUP_ROOT = PROJECT_ROOT / ".atlas_apply_backup"
VALIDATION_ROOT = PROJECT_ROOT / ".atlas_validation"

logger = logging.getLogger(__name__)


def positive_integer(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be an integer."
        ) from exc

    if value < 1:
        raise RuntimeError(
            f"{name} must be at least 1."
        )

    return value


def non_negative_float(
    name: str,
    default: float,
) -> float:
    raw_value = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be numeric."
        ) from exc

    if value < 0:
        raise RuntimeError(
            f"{name} cannot be negative."
        )

    return value


def minimum_float(
    name: str,
    default: float,
    minimum: float,
) -> float:
    value = non_negative_float(
        name,
        default,
    )

    if value < minimum:
        raise RuntimeError(
            f"{name} must be at least {minimum}."
        )

    return value


def boolean_setting(
    name: str,
    default: bool,
) -> bool:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise RuntimeError(
        f"{name} must be true or false."
    )


def build_pipeline() -> AtlasPipeline:
    return AtlasPipeline(
        manager=OpenAIManager(
            client=ClientFactory.create(
                "openai"
            ),
        ),
        worker=GeminiWorker(
            client=ClientFactory.create(
                "gemini"
            ),
        ),
        prompt_builder=PromptBuilder(),
        parser=WorkerOutputParser(),
        review_parser=ReviewParser(),
        workspace_writer=WorkspaceWriter(
            staging_root=STAGING_ROOT,
        ),
        test_runner=StagingTestRunner(
            staging_root=STAGING_ROOT,
            timeout_seconds=config.CLIENT_TIMEOUT,
        ),
        max_iterations=(
            config.MAX_REVIEW_ITERATIONS
        ),
    )


def build_base_release_coordinator(
) -> ReleaseCoordinator:
    git_engine = GitEngine(
        repository_root=PROJECT_ROOT,
        timeout_seconds=config.CLIENT_TIMEOUT,
    )

    diff_engine = WorkspaceDiffEngine(
        project_root=PROJECT_ROOT,
        staging_root=STAGING_ROOT,
    )

    apply_engine = TransactionalApplyEngine(
        project_root=PROJECT_ROOT,
        staging_root=STAGING_ROOT,
        backup_root=BACKUP_ROOT,
    )

    return ReleaseCoordinator(
        project_root=PROJECT_ROOT,
        staging_root=STAGING_ROOT,
        git_engine=git_engine,
        apply_engine=apply_engine,
        diff_engine=diff_engine,
    )


def build_release_coordinator(
    *,
    branch: str = "main",
) -> LockedReleaseCoordinator:
    cleaned_branch = branch.strip()

    if not cleaned_branch:
        raise RuntimeError(
            "Release branch cannot be empty."
        )

    minimum_free_megabytes = (
        positive_integer(
            "ATLAS_MINIMUM_FREE_DISK_MB",
            256,
        )
    )

    minimum_free_percent = (
        non_negative_float(
            "ATLAS_MINIMUM_FREE_DISK_PERCENT",
            5.0,
        )
    )

    if minimum_free_percent > 100:
        raise RuntimeError(
            "ATLAS_MINIMUM_FREE_DISK_PERCENT "
            "cannot exceed 100."
        )

    delegate = (
        build_base_release_coordinator()
    )

    return LockedReleaseCoordinator(
        delegate=delegate,
        operation_lock=(
            RepositoryOperationLock(
                DATA_ROOT
                / "repository_release.lock",
                operation="apply-commit-push",
            )
        ),
        preflight=ProductionPreflight(
            repository_root=PROJECT_ROOT,
            disk_guard=DiskPressureGuard(
                PROJECT_ROOT,
                minimum_free_bytes=(
                    minimum_free_megabytes
                    * 1024
                    * 1024
                ),
                minimum_free_percent=(
                    minimum_free_percent
                ),
            ),
            expected_branch=cleaned_branch,
        ),
    )


def build_runtime_observer(
) -> RuntimeObserver:
    return RuntimeObserver(
        heartbeat_store=RuntimeHeartbeatStore(
            DATA_ROOT
            / "runtime_heartbeat.json"
        ),
        alert_store=RuntimeAlertStore(
            DATA_ROOT / "runtime_alerts.json",
            max_alerts=positive_integer(
                "ATLAS_RUNTIME_MAX_ALERTS",
                200,
            ),
        ),
        disk_cleaner=RuntimeDiskCleaner(
            roots=(
                BACKUP_ROOT,
                VALIDATION_ROOT,
            ),
            minimum_age_seconds=(
                non_negative_float(
                    "ATLAS_RUNTIME_CLEANUP_AGE_SECONDS",
                    86400.0,
                )
            ),
        ),
        cleanup_interval_cycles=(
            positive_integer(
                "ATLAS_RUNTIME_CLEANUP_INTERVAL_CYCLES",
                120,
            )
        ),
    )


def build_runtime_service(
    *,
    observer: RuntimeObserver | None = None,
) -> DirectiveAwareRuntimeService:
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    roadmap_store = RoadmapTaskStore(
        storage_path=(
            DATA_ROOT / "roadmap_tasks.json"
        ),
    )

    workflow_store = WorkflowStateStore(
        storage_path=(
            DATA_ROOT
            / "orchestration_workflows.json"
        ),
    )

    branch = os.getenv(
        "ATLAS_RUNTIME_BRANCH",
        "main",
    ).strip()

    remote = os.getenv(
        "ATLAS_RUNTIME_REMOTE",
        "origin",
    ).strip()

    if not branch:
        raise RuntimeError(
            "ATLAS_RUNTIME_BRANCH cannot be empty."
        )

    if not remote:
        raise RuntimeError(
            "ATLAS_RUNTIME_REMOTE cannot be empty."
        )

    orchestrator = ContinuousOrchestrator(
        pipeline=build_pipeline(),
        release_coordinator=(
            build_release_coordinator(
                branch=branch
            )
        ),
        workflow_store=workflow_store,
        autonomy_policy=AutonomyPolicy(
            development_branches={
                branch,
            },
        ),
        remote=remote,
        branch=branch,
        push=boolean_setting(
            "ATLAS_RUNTIME_PUSH",
            True,
        ),
    )

    recovery_manager = WorkflowRecoveryManager(
        orchestrator=orchestrator,
        workflow_store=workflow_store,
    )

    directive_store = ArchitectDirectiveStore(
        storage_path=(
            DATA_ROOT
            / "architect_directives.json"
        ),
    )

    directive_importer = RoadmapDirectiveImporter(
        directive_store=directive_store,
        roadmap_store=roadmap_store,
    )

    retry_policy = RuntimeRetryPolicy(
        state_store=RetryStateStore(
            DATA_ROOT / "runtime_retries.json"
        ),
        max_attempts=positive_integer(
            "ATLAS_RUNTIME_MAX_ATTEMPTS",
            4,
        ),
        initial_delay_seconds=(
            non_negative_float(
                "ATLAS_RUNTIME_RETRY_INITIAL_SECONDS",
                30.0,
            )
        ),
        multiplier=minimum_float(
            "ATLAS_RUNTIME_RETRY_MULTIPLIER",
            2.0,
            1.0,
        ),
        max_delay_seconds=(
            non_negative_float(
                "ATLAS_RUNTIME_RETRY_MAX_SECONDS",
                900.0,
            )
        ),
    )

    return DirectiveAwareRuntimeService(
        roadmap_store=roadmap_store,
        roadmap_selector=RoadmapTaskSelector(
            roadmap_store
        ),
        orchestrator=orchestrator,
        recovery_manager=recovery_manager,
        process_lock=RuntimeProcessLock(
            DATA_ROOT
            / "continuous_orchestrator.lock"
        ),
        retry_policy=retry_policy,
        user_id=positive_integer(
            "ATLAS_RUNTIME_USER_ID",
            1,
        ),
        idle_seconds=non_negative_float(
            "ATLAS_RUNTIME_IDLE_SECONDS",
            30.0,
        ),
        directive_importer=directive_importer,
        cycle_callback=(
            observer.handle_cycle
            if observer is not None
            else None
        ),
        history_limit=positive_integer(
            "ATLAS_RUNTIME_HISTORY_LIMIT",
            100,
        ),
    )


def log_cycle(
    result: RuntimeCycleResult,
) -> None:
    task_id = (
        result.roadmap_task.task_id
        if result.roadmap_task is not None
        else "none"
    )

    logger.info(
        "Runtime cycle "
        "status=%s task=%s "
        "resumed=%s message=%s",
        result.status.value,
        task_id,
        result.resumed,
        result.message,
    )


def main() -> None:
    setup_logger(
        "atlas-lite.runtime"
    )

    stop_event = Event()
    observer = build_runtime_observer()

    def request_stop(
        signum: int,
        frame: object,
    ) -> None:
        logger.info(
            "Stop signal received: %s",
            signum,
        )
        stop_event.set()

    signal.signal(
        signal.SIGTERM,
        request_stop,
    )

    signal.signal(
        signal.SIGINT,
        request_stop,
    )

    service = build_runtime_service(
        observer=observer
    )

    observer.mark_started()

    logger.info(
        "Atlas continuous runtime starting."
    )

    try:
        service.run_forever(
            stop_event=stop_event,
        )
    finally:
        observer.mark_stopped()

        logger.info(
            "Atlas continuous runtime stopped."
        )


if __name__ == "__main__":
    main()
