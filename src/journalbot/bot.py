"""Discord bot construction and event handlers."""

import logging
import os

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

COMMANDS_HELP = "\n".join(
    (
        "Available commands:",
        "- `Bot: describe` — describe JournalBot's purpose.",
        "- `Bot: help` or `Bot: commands` — show this command list.",
    )
)


class JournalBot(commands.Bot):
    """Minimal Discord bot for the JournalBot application."""

    _ready_announcement_sent: bool = False

    async def setup_hook(self) -> None:
        """Run one-time asynchronous setup before the bot connects."""
        LOGGER.info("JournalBot setup complete")

    async def on_ready(self) -> None:
        """Log a connection and optionally announce that the bot is ready."""
        if self.user is not None:
            LOGGER.info("Connected to Discord as %s (ID: %s)", self.user, self.user.id)
        LOGGER.info(
            "Guilds visible to this bot: %s",
            [(guild.name, guild.id) for guild in self.guilds],
        )

        if self._ready_announcement_sent:
            return

        channel_id = _get_ready_channel_id()
        if channel_id is None:
            return

        try:
            channel = await self.fetch_channel(channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                LOGGER.error(
                    "Configured ready channel ID %s cannot receive messages", channel_id
                )
                return
            await channel.send("Ready to rumble")
        except discord.HTTPException:
            LOGGER.exception(
                "Could not announce readiness in channel ID %s", channel_id
            )
            return

        self._ready_announcement_sent = True

    async def on_message(self, message: discord.Message) -> None:
        """Respond to the bot's supported text commands."""
        if message.author.bot:
            return

        if message.content == "Bot: describe":
            LOGGER.info("Bot description invoked")
            await message.channel.send(
                "I am JournalBot, a Discord bot for keeping a structured journal "
                "for Pathfinder 2e campaigns."
            )

        if message.content in {"Bot: help", "Bot: commands"}:
            LOGGER.info("Bot command list invoked")
            await message.channel.send(COMMANDS_HELP)

        await self.process_commands(message)


def _get_ready_channel_id() -> int | None:
    """Return the optional configured channel for the ready announcement."""
    channel_id = os.environ.get("DISCORD_READY_CHANNEL_ID")
    if channel_id is None:
        return None

    try:
        return int(channel_id)
    except ValueError:
        LOGGER.error("DISCORD_READY_CHANNEL_ID must be a numeric Discord channel ID")
        return None


def create_bot() -> JournalBot:
    """Create the configured JournalBot instance."""
    intents = discord.Intents.default()
    intents.message_content = True
    return JournalBot(command_prefix="!", intents=intents)
