from __future__ import annotations

import logging

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
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStore,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)
from discord_gateway.bot import (
    AtlasDiscordBot,
)
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
)
from services.code_validator import (
    PythonCodeValidator,
)
from utils.logger import setup_logger


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
                ".atlas_data/"
                "conversation_memory.json"
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
    roadmap_store = RoadmapTaskStore(
        storage_path=(
            ".atlas_data/roadmap_tasks.json"
        )
    )

    workflow_store = WorkflowStateStore(
        storage_path=(
            ".atlas_data/"
            "orchestration_workflows.json"
        )
    )

    return DiscordRuntimeControls(
        roadmap_store=roadmap_store,
        workflow_store=workflow_store,
        roadmap_selector=RoadmapTaskSelector(
            roadmap_store
        ),
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
    )

    bot.run(
        config.DISCORD_BOT_TOKEN
    )


if __name__ == "__main__":
    main()
