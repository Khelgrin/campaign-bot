"""Discord bot construction and event handlers."""

import logging

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class JournalBot(commands.Bot):
    """Minimal Discord bot for the JournalBot application."""

    async def setup_hook(self) -> None:
        """Run one-time asynchronous setup before the bot connects."""
        LOGGER.info("JournalBot setup complete")

    async def on_ready(self) -> None:
        """Log a successful connection to Discord."""
        if self.user is not None:
            LOGGER.info("Connected to Discord as %s (ID: %s)", self.user, self.user.id)


def create_bot() -> JournalBot:
    """Create the configured JournalBot instance."""
    intents = discord.Intents.default()
    return JournalBot(command_prefix="!", intents=intents)

