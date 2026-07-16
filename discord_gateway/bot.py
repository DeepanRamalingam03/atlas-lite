from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from assistants.service import AtlasAssistant
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
)


logger = logging.getLogger(__name__)


class AtlasDiscordBot(commands.Bot):
    """
    Discord communication gateway for Atlas Lite.

    Commands:
    - !ping
    - !status
    - !ask <question>
    - !reset
    - !runtime
    - !roadmap
    - !workflow [workflow_id]
    - !pause <roadmap_task_id>
    - !resume <roadmap_task_id>
    """

    DISCORD_MESSAGE_LIMIT = 1900

    def __init__(
        self,
        guild_id: int,
        channel_id: int,
        allowed_user_id: int,
        assistant: AtlasAssistant,
        runtime_controls: DiscordRuntimeControls | None = None,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        self.allowed_guild_id = guild_id
        self.allowed_channel_id = channel_id
        self.allowed_user_id = allowed_user_id
        self.assistant = assistant
        self.runtime_controls = (
            runtime_controls
            or DiscordRuntimeControls()
        )
        self._startup_message_sent = False

        self._register_commands()

    def _register_commands(self) -> None:
        @self.command(name="ping")
        async def ping_command(
            context: commands.Context[AtlasDiscordBot],
        ) -> None:
            latency_ms = round(
                self.latency * 1000
            )

            await context.send(
                "Atlas Lite connected. "
                f"Latency: `{latency_ms} ms`"
            )

        @self.command(name="status")
        async def status_command(
            context: commands.Context[AtlasDiscordBot],
        ) -> None:
            history_size = (
                self.assistant.history_size(
                    context.author.id
                )
            )

            runtime = (
                self.runtime_controls.runtime_status(
                    context.author.id
                )
            )

            message = (
                "**Atlas Lite Status**\n"
                "Manager: OpenAI\n"
                "Worker: Gemini\n"
                "Discord gateway: Connected\n"
                f"Conversation history turns: "
                f"`{history_size}`\n"
                "AI assistant: Ready\n\n"
                f"{runtime.message}"
            )

            for chunk in self._split_message(
                message
            ):
                await context.send(chunk)

        @self.command(name="ask")
        async def ask_command(
            context: commands.Context[AtlasDiscordBot],
            *,
            question: str,
        ) -> None:
            cleaned_question = question.strip()

            if not cleaned_question:
                await context.send(
                    "Usage: `!ask <your question>`"
                )
                return

            async with context.typing():
                try:
                    answer = await asyncio.to_thread(
                        self.assistant.ask,
                        context.author.id,
                        cleaned_question,
                    )
                except Exception as exc:
                    logger.exception(
                        "Atlas AI request failed."
                    )

                    await context.send(
                        "Atlas AI request failed: "
                        f"`{type(exc).__name__}: {exc}`"
                    )
                    return

            for chunk in self._split_message(
                answer
            ):
                await context.send(chunk)

        @self.command(name="reset")
        async def reset_command(
            context: commands.Context[AtlasDiscordBot],
        ) -> None:
            self.assistant.clear_history(
                context.author.id
            )

            await context.send(
                "Atlas conversation history cleared."
            )

        @self.command(name="runtime")
        async def runtime_command(
            context: commands.Context[AtlasDiscordBot],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls.runtime_status,
                context.author.id,
            )

            for chunk in self._split_message(
                result.message
            ):
                await context.send(chunk)

        @self.command(name="roadmap")
        async def roadmap_command(
            context: commands.Context[AtlasDiscordBot],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls.roadmap_status
            )

            for chunk in self._split_message(
                result.message
            ):
                await context.send(chunk)

        @self.command(name="workflow")
        async def workflow_command(
            context: commands.Context[AtlasDiscordBot],
            workflow_id: str | None = None,
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls.workflow_status,
                context.author.id,
                workflow_id,
            )

            for chunk in self._split_message(
                result.message
            ):
                await context.send(chunk)

        @self.command(name="pause")
        async def pause_command(
            context: commands.Context[AtlasDiscordBot],
            task_id: str,
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls.pause_task,
                task_id,
            )

            await context.send(
                result.message
            )

        @self.command(name="resume")
        async def resume_command(
            context: commands.Context[AtlasDiscordBot],
            task_id: str,
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls.resume_task,
                task_id,
            )

            await context.send(
                result.message
            )

    async def setup_hook(self) -> None:
        logger.info(
            "Atlas Discord setup completed."
        )

    async def on_ready(self) -> None:
        if self.user is None:
            logger.error(
                "Discord connected without a bot user."
            )
            return

        logger.info(
            "Atlas Discord connected as %s (%s)",
            self.user,
            self.user.id,
        )

        if self._startup_message_sent:
            return

        channel = self.get_channel(
            self.allowed_channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            logger.error(
                "Configured Discord channel "
                "was not found: %s",
                self.allowed_channel_id,
            )
            return

        await channel.send(
            "**Atlas Lite is online**\n"
            "Commands:\n"
            "`!ask <question>`\n"
            "`!status`\n"
            "`!runtime`\n"
            "`!roadmap`\n"
            "`!workflow [workflow_id]`\n"
            "`!pause <roadmap_task_id>`\n"
            "`!resume <roadmap_task_id>`\n"
            "`!ping`\n"
            "`!reset`"
        )

        self._startup_message_sent = True

    async def on_command_error(
        self,
        context: commands.Context[AtlasDiscordBot],
        error: commands.CommandError,
    ) -> None:
        if isinstance(
            error,
            commands.CommandNotFound,
        ):
            return

        if isinstance(
            error,
            commands.MissingRequiredArgument,
        ):
            await context.send(
                "Missing input. Check command usage with "
                "`!status`."
            )
            return

        original_error = getattr(
            error,
            "original",
            error,
        )

        logger.exception(
            "Discord command failed.",
            exc_info=original_error,
        )

        await context.send(
            "Atlas command failed: "
            f"`{type(original_error).__name__}: "
            f"{original_error}`"
        )

    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        if message.author.bot:
            return

        if not self._is_allowed(
            guild_id=(
                message.guild.id
                if message.guild is not None
                else None
            ),
            channel_id=message.channel.id,
            user_id=message.author.id,
        ):
            return

        await self.process_commands(
            message
        )

    def _is_allowed(
        self,
        guild_id: int | None,
        channel_id: int | None,
        user_id: int,
    ) -> bool:
        return (
            guild_id
            == self.allowed_guild_id
            and channel_id
            == self.allowed_channel_id
            and user_id
            == self.allowed_user_id
        )

    @classmethod
    def _split_message(
        cls,
        content: str,
    ) -> list[str]:
        cleaned_content = content.strip()

        if not cleaned_content:
            return [
                "Atlas returned an empty response."
            ]

        chunks: list[str] = []
        remaining = cleaned_content

        while (
            len(remaining)
            > cls.DISCORD_MESSAGE_LIMIT
        ):
            split_at = remaining.rfind(
                "\n",
                0,
                cls.DISCORD_MESSAGE_LIMIT,
            )

            if split_at <= 0:
                split_at = (
                    cls.DISCORD_MESSAGE_LIMIT
                )

            chunk = remaining[
                :split_at
            ].strip()

            if chunk:
                chunks.append(chunk)

            remaining = remaining[
                split_at:
            ].strip()

        if remaining:
            chunks.append(remaining)

        return chunks
