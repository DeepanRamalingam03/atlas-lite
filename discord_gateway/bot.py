from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from assistants.service import AtlasAssistant
from core.usage.token_ledger import (
    TokenUsageLedger,
)
from discord_gateway.runtime_controls import (
    DiscordRuntimeControls,
)
from discord_gateway.usage_controls import (
    DiscordUsageControls,
)


logger = logging.getLogger(__name__)


class AtlasDiscordBot(commands.Bot):
    """
    Discord communication and runtime control gateway for Atlas Lite.

    Commands:
    - !ping
    - !status
    - !ask <question>
    - !reset
    - !runtime
    - !roadmap
    - !workflow [workflow_id]
    - !heartbeat
    - !usage [today|week|month|all] [all|openai|gemini]
    - !cost [today|week|month|all] [all|openai|gemini]
    - !alerts
    - !ackalerts
    - !addtask <priority> | <title> | <goal>
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
        runtime_controls: (
            DiscordRuntimeControls | None
        ) = None,
        usage_controls: (
            DiscordUsageControls | None
        ) = None,
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
        self.usage_controls = (
            usage_controls
            or DiscordUsageControls(
                ledger=TokenUsageLedger()
            )
        )
        self._startup_message_sent = False

        self._register_commands()

    def _register_commands(self) -> None:
        @self.command(name="ping")
        async def ping_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
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
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            history_size = (
                self.assistant.history_size(
                    context.author.id
                )
            )

            runtime = await asyncio.to_thread(
                self.runtime_controls.runtime_status,
                context.author.id,
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

            await self._send_chunks(
                context,
                message,
            )

        @self.command(name="ask")
        async def ask_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
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
                        f"`{type(exc).__name__}: "
                        f"{exc}`"
                    )
                    return

            await self._send_chunks(
                context,
                answer,
            )

        @self.command(name="reset")
        async def reset_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            self.assistant.clear_history(
                context.author.id
            )

            await context.send(
                "Atlas conversation history cleared."
            )

        @self.command(name="runtime")
        async def runtime_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls.runtime_status,
                context.author.id,
            )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="roadmap")
        async def roadmap_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls
                .roadmap_status
            )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="workflow")
        async def workflow_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
            workflow_id: str | None = None,
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls
                .workflow_status,
                context.author.id,
                workflow_id,
            )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="heartbeat")
        async def heartbeat_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls
                .heartbeat_status
            )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="usage")
        async def usage_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
            period: str = "today",
            provider: str = "all",
        ) -> None:
            selected_period = (
                period.strip().lower()
                if period
                else "today"
            )

            selected_provider = (
                provider.strip().lower()
                if provider
                else "all"
            )

            if selected_period in {
                "help",
                "commands",
            }:
                result = await asyncio.to_thread(
                    self.usage_controls
                    .help_message
                )
            else:
                result = await asyncio.to_thread(
                    self.usage_controls.usage,
                    selected_period,
                    selected_provider,
                )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="cost")
        async def cost_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
            period: str = "today",
            provider: str = "all",
        ) -> None:
            selected_period = (
                period.strip().lower()
                if period
                else "today"
            )

            selected_provider = (
                provider.strip().lower()
                if provider
                else "all"
            )

            if selected_period in {
                "help",
                "commands",
            }:
                result = await asyncio.to_thread(
                    self.usage_controls
                    .help_message
                )
            else:
                result = await asyncio.to_thread(
                    self.usage_controls.cost,
                    selected_period,
                    selected_provider,
                )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="alerts")
        async def alerts_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls
                .alerts_status
            )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="ackalerts")
        async def acknowledge_alerts_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
        ) -> None:
            result = await asyncio.to_thread(
                self.runtime_controls
                .acknowledge_alerts
            )

            await context.send(
                result.message
            )

        @self.command(name="addtask")
        async def add_task_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
            *,
            directive: str,
        ) -> None:
            try:
                priority, title, goal = (
                    self._parse_add_task(
                        directive
                    )
                )
            except ValueError as exc:
                await context.send(
                    f"{exc}\n"
                    "Usage: "
                    "`!addtask "
                    "<priority> | <title> | <goal>`"
                )
                return

            result = await asyncio.to_thread(
                self.runtime_controls.add_directive,
                title=title,
                goal=goal,
                priority=priority,
                source=(
                    "discord-architect:"
                    f"{context.author.id}"
                ),
            )

            await self._send_chunks(
                context,
                result.message,
            )

        @self.command(name="pause")
        async def pause_command(
            context: commands.Context[
                AtlasDiscordBot
            ],
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
            context: commands.Context[
                AtlasDiscordBot
            ],
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
            "`!heartbeat`\n"
            "`!usage [today|week|month|all] "
            "[all|openai|gemini]`\n"
            "`!cost [today|week|month|all] "
            "[all|openai|gemini]`\n"
            "`!alerts`\n"
            "`!ackalerts`\n"
            "`!addtask "
            "<priority> | <title> | <goal>`\n"
            "`!pause <roadmap_task_id>`\n"
            "`!resume <roadmap_task_id>`\n"
            "`!ping`\n"
            "`!reset`"
        )

        self._startup_message_sent = True

    async def on_command_error(
        self,
        context: commands.Context[
            AtlasDiscordBot
        ],
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
                "Missing input. "
                "Check command usage with "
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

    async def _send_chunks(
        self,
        context: commands.Context[
            AtlasDiscordBot
        ],
        content: str,
    ) -> None:
        for chunk in self._split_message(
            content
        ):
            await context.send(chunk)

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

    @staticmethod
    def _parse_add_task(
        content: str,
    ) -> tuple[int, str, str]:
        parts = [
            part.strip()
            for part in content.split(
                "|",
                maxsplit=2,
            )
        ]

        if len(parts) != 3:
            raise ValueError(
                "Task input must contain priority, "
                "title, and goal separated by `|`."
            )

        priority_text, title, goal = parts

        try:
            priority = int(priority_text)
        except ValueError as exc:
            raise ValueError(
                "Task priority must be an integer."
            ) from exc

        if priority < 0:
            raise ValueError(
                "Task priority cannot be negative."
            )

        if not title:
            raise ValueError(
                "Task title cannot be empty."
            )

        if not goal:
            raise ValueError(
                "Task goal cannot be empty."
            )

        return priority, title, goal

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
