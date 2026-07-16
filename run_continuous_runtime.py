from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from threading import Event

import config
from apply.engine import TransactionalApplyEngine
from clients.factory import ClientFactory
from core.orchestration.autonomy_policy import AutonomyPolicy
from core.orchestration.continuous_loop import ContinuousOrchestrator
from core.orchestration.directive_importer import (
    ArchitectDirectiveStore,
    RoadmapDirectiveImporter,
)
from core.orchestration.directive_runtime import (
    DirectiveAwareRuntimeService,
)
from core.orchestration.recovery_manager import WorkflowRecoveryManager
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStore,
)
from core.orchestration.runtime_lock import RuntimeProcessLock
from core.orchestration.runtime_service import (
    ContinuousRuntimeService,
    RuntimeCycleResult,
)
from core.orchestration.state_store import WorkflowStateStore
from git_tools.engine import GitEngine
from managers.openai_manager import OpenAIManager
from orchestrator.pipeline import AtlasPipeline
from release.coordinator import ReleaseCoordinator
from services.prompt_builder import PromptBuilder
from services.review_parser import ReviewParser
from services.worker_output_parser import WorkerOutputParser
from testing.runner import StagingTestRunner
from utils.logger import setup_logger
from workers.gemini_worker import GeminiWorker
from workspace.diff_engine import WorkspaceDiffEngine
from workspace.writer import WorkspaceWriter


PROJECT_ROOT = Path(__file__).resolve().parent
STAGING_ROOT = PROJECT_ROOT / ".atlas_staging"
DATA_ROOT = PROJECT_ROOT / ".atlas_data"
BACKUP_ROOT = PROJECT_ROOT / ".atlas_apply_backup"

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
            client=ClientFactory.create("openai"),
        ),
        worker=GeminiWorker(
            client=ClientFactory.create("gemini"),
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
        max_iterations=config.MAX_REVIEW_ITERATIONS,
    )


def build_release_coordinator() -> ReleaseCoordinator:
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


def build_runtime_service() -> DirectiveAwareRuntimeService:
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    roadmap_store = RoadmapTaskStore(
        storage_path=DATA_ROOT / "roadmap_tasks.json",
    )

    workflow_store = WorkflowStateStore(
        storage_path=(
            DATA_ROOT / "orchestration_workflows.json"
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
        release_coordinator=build_release_coordinator(),
        workflow_store=workflow_store,
        autonomy_policy=AutonomyPolicy(
            development_branches={branch},
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
            DATA_ROOT / "architect_directives.json"
        ),
    )

    directive_importer = RoadmapDirectiveImporter(
        directive_store=directive_store,
        roadmap_store=roadmap_store,
    )

    return DirectiveAwareRuntimeService(
        roadmap_store=roadmap_store,
        roadmap_selector=RoadmapTaskSelector(
            roadmap_store
        ),
        orchestrator=orchestrator,
        recovery_manager=recovery_manager,
        process_lock=RuntimeProcessLock(
            DATA_ROOT / "continuous_orchestrator.lock"
        ),
        user_id=positive_integer(
            "ATLAS_RUNTIME_USER_ID",
            1,
        ),
        idle_seconds=non_negative_float(
            "ATLAS_RUNTIME_IDLE_SECONDS",
            30.0,
        ),
        directive_importer=directive_importer,
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
        "Runtime cycle status=%s task=%s resumed=%s message=%s",
        result.status.value,
        task_id,
        result.resumed,
        result.message,
    )


def main() -> None:
    setup_logger("atlas-lite.runtime")

    stop_event = Event()

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

    service = build_runtime_service()

    logger.info(
        "Atlas continuous runtime starting."
    )

    results = service.run_forever(
        stop_event=stop_event,
    )

    for result in results[-10:]:
        log_cycle(result)

    logger.info(
        "Atlas continuous runtime stopped."
    )


if __name__ == "__main__":
    main()
