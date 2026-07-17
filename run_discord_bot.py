from __future__ import annotations

import logging
from pathlib import Path

import config
from assistants.service import AtlasAssistant
from clients.factory import ClientFactory
from core.assistant_manager import (
    AtlasAssistantManager,
)
from core.intent_router import IntentRouter
from core.memory_store import (
    PersistentMemoryStore,
)
from core.orchestration.directive_importer import (
    ArchitectDirectiveStore,
)
from core.orchestration.observability import (
    RuntimeAlertStore,
    RuntimeHeartbeatStore,
)
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStore,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)
from core.usage.token_ledger import (
    TokenUsageLedger,
)
from discord_gateway.bot import AtlasDiscordBot
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
)
from discord_gateway.usage_controls import (
    DiscordUsageControls,
)
from services.code_validator import (
    PythonCodeValidator,
)
from utils.logger import setup_logger


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / ".atlas_data"


def required_integer(
    name: str,
    value: str | None,
) -> int:
    if not value or not value.strip():
        raise RuntimeError(
            "Missing required Discord "
            f"configuration: {name}"
        )

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must contain a "
            "numeric Discord ID."
        ) from exc


def build_assistant() -> AtlasAssistant:
    manager = AtlasAssistantManager(
        clients={
            "openai": ClientFactory.create(
                "openai"
            ),
            "gemini": ClientFactory.create(
                "gemini"
            ),
        },
        router=IntentRouter(),
        memory=PersistentMemoryStore(
            storage_path=(
                DATA_ROOT
                / "conversation_memory.json"
            ),
            max_turns_per_user=12,
        ),
        code_validator=PythonCodeValidator(),
        max_code_retries=2,
    )

    return AtlasAssistant(
        manager=manager
    )


def build_runtime_controls(
) -> DiscordRuntimeControls:
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    roadmap_store = RoadmapTaskStore(
        storage_path=(
            DATA_ROOT / "roadmap_tasks.json"
        )
    )

    workflow_store = WorkflowStateStore(
        storage_path=(
            DATA_ROOT
            / "orchestration_workflows.json"
        )
    )

    directive_store = ArchitectDirectiveStore(
        storage_path=(
            DATA_ROOT
            / "architect_directives.json"
        )
    )

    heartbeat_store = RuntimeHeartbeatStore(
        storage_path=(
            DATA_ROOT
            / "runtime_heartbeat.json"
        )
    )

    alert_store = RuntimeAlertStore(
        storage_path=(
            DATA_ROOT / "runtime_alerts.json"
        )
    )

    return DiscordRuntimeControls(
        roadmap_store=roadmap_store,
        workflow_store=workflow_store,
        roadmap_selector=RoadmapTaskSelector(
            roadmap_store
        ),
        directive_store=directive_store,
        heartbeat_store=heartbeat_store,
        alert_store=alert_store,
    )


def build_usage_controls(
) -> DiscordUsageControls:
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    ledger = TokenUsageLedger(
        storage_path=(
            DATA_ROOT
            / "ai_token_usage.json"
        )
    )

    return DiscordUsageControls(
        ledger=ledger
    )


def main() -> None:
    setup_logger(
        "atlas-lite.discord"
    )

    logging.getLogger(
        "discord"
    ).setLevel(logging.INFO)

    if not config.DISCORD_BOT_TOKEN:
        raise RuntimeError(
            "Missing required configuration: "
            "DISCORD_BOT_TOKEN"
        )

    bot = AtlasDiscordBot(
        guild_id=required_integer(
            "DISCORD_GUILD_ID",
            config.DISCORD_GUILD_ID,
        ),
        channel_id=required_integer(
            "DISCORD_CHANNEL_ID",
            config.DISCORD_CHANNEL_ID,
        ),
        allowed_user_id=required_integer(
            "DISCORD_ALLOWED_USER_ID",
            config.DISCORD_ALLOWED_USER_ID,
        ),
        assistant=build_assistant(),
        runtime_controls=(
            build_runtime_controls()
        ),
        usage_controls=(
            build_usage_controls()
        ),
    )

    bot.run(
        config.DISCORD_BOT_TOKEN
    )


if __name__ == "__main__":
    main()
