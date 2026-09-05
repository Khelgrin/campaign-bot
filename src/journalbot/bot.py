"""Discord bot construction and event handlers."""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import discord
from discord.ext import commands

from journalbot.campaigns import (
    CampaignError,
    CampaignStore,
    NoCampaignSelectedError,
)
from journalbot.database import get_database_path
from journalbot.sessions import SessionError, SessionStore

LOGGER = logging.getLogger(__name__)

LOGGED_COMMANDS = frozenset(
    {
        "start-campaign",
        "use-campaign",
        "list-campaign",
        "read-campaign",
        "update-campaign",
        "end-campaign",
        "start-session",
        "use-session",
        "list-session",
        "read-session",
        "update-session",
        "end-session",
    }
)

COMMANDS_HELP = "\n".join(
    (
        "Available commands:",
        "- `Bot: describe` — describe JournalBot's purpose.",
        "- `Bot: help` or `Bot: commands` — show this command list.",
        "- `!start-campaign <title> [description]` — create a campaign.",
        "- `!use-campaign <id or title>` — select a campaign.",
        "- `!list-campaign` — list campaigns.",
        "- `!read-campaign <id or title>` — show campaign details.",
        "- `!update-campaign <id or title> [title] [description]` — update metadata.",
        "- `!end-campaign` — end the selected campaign.",
        "- `!start-session [title] [description]` — create a session.",
        "- `!use-session <number, id, or title>` — select a session.",
        "- `!list-session` — list sessions for the current campaign.",
        "- `!read-session <id or title>` — show session details.",
        "- `!update-session <id or title> [title] [description] [played_at]` — "
        "update session metadata.",
        "- `!end-session` — end the selected session.",
    )
)


class CampaignCommands(commands.Cog):
    """Discord commands for campaign lifecycle and guild context."""

    def __init__(self, store: CampaignStore) -> None:
        self.store = store
        self.sessions = SessionStore(store.database_path)

    async def _require_guild(self, ctx: commands.Context) -> int | None:
        if ctx.guild is None:
            await ctx.send("Campaign commands can only be used in a Discord server.")
            return None
        return ctx.guild.id

    @commands.command(name="start-campaign")
    async def start_campaign(
        self, ctx: commands.Context, title: str, *, description: str = ""
    ) -> None:
        """Create and select a campaign."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign = self.store.create(guild_id, title, description)
        except (CampaignError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Campaign **{campaign.title}** created and selected "
            f"(ID: {campaign.id})."
        )

    @commands.command(name="use-campaign")
    async def use_campaign(
        self, ctx: commands.Context, *, identifier: str
    ) -> None:
        """Select a campaign by ID or exact title."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign = self.store.select(guild_id, identifier)
        except CampaignError as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Selected campaign **{campaign.title}** (ID: {campaign.id})."
        )

    @commands.command(name="list-campaign")
    async def list_campaign(self, ctx: commands.Context) -> None:
        """List all campaigns."""
        campaigns = self.store.list()
        if not campaigns:
            await ctx.send("No campaigns exist yet.")
            return
        selected_id = None
        if ctx.guild is not None:
            try:
                selected_id = self.store.current(ctx.guild.id).id
            except NoCampaignSelectedError:
                pass
        lines = [
            f"{'* ' if campaign.id == selected_id else ''}{campaign.id}: "
            f"{campaign.title} [{campaign.status}]"
            for campaign in campaigns
        ]
        await ctx.send("\n".join(lines))

    @commands.command(name="read-campaign")
    async def read_campaign(
        self, ctx: commands.Context, *, identifier: str
    ) -> None:
        """Display campaign details."""
        try:
            campaign = self.store.find(identifier)
        except CampaignError as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"ID: {campaign.id}\nTitle: {campaign.title}\n"
            f"Description: {campaign.description or '(none)'}\n"
            f"Status: {campaign.status}\nCreated at: {campaign.created_at}\n"
            f"Ended at: {campaign.ended_at or '(ongoing)'}"
        )

    @commands.command(name="update-campaign")
    async def update_campaign(
        self,
        ctx: commands.Context,
        identifier: str,
        title: str | None = None,
        *,
        description: str | None = None,
    ) -> None:
        """Update campaign title and/or description."""
        try:
            campaign = self.store.update(identifier, title, description)
        except (CampaignError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Campaign updated: **{campaign.title}** (ID: {campaign.id})."
        )

    @commands.command(name="end-campaign")
    async def end_campaign(self, ctx: commands.Context) -> None:
        """End the current campaign."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign = self.store.end_current(guild_id)
        except CampaignError as error:
            await ctx.send(str(error))
            return
        await ctx.send(f"Campaign **{campaign.title}** ended.")

    @commands.command(name="start-session")
    async def start_session(
        self, ctx: commands.Context, title: str | None = None, *,
        description: str = ""
    ) -> None:
        """Create and select a session for the current campaign."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.create(guild_id, title, description)
        except (CampaignError, SessionError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Session **{session.title}** created and selected "
            f"(ID: {session.id}, number: {session.number})."
        )

    @commands.command(name="use-session")
    async def use_session(self, ctx: commands.Context, *, identifier: str) -> None:
        """Select a session by ID or exact title."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.select(guild_id, identifier)
        except SessionError as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Selected session **{session.title}** "
            f"(ID: {session.id}, number: {session.number})."
        )

    @commands.command(name="list-session")
    async def list_session(self, ctx: commands.Context) -> None:
        """List sessions for the current campaign."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            sessions = self.sessions.list_current_campaign(guild_id)
        except (CampaignError, SessionError) as error:
            await ctx.send(str(error))
            return
        if not sessions:
            await ctx.send("No sessions exist for the current campaign.")
            return
        try:
            selected_id = self.sessions.current(guild_id).id
        except SessionError:
            selected_id = None
        await ctx.send(
            "\n".join(
                f"{'* ' if item.id == selected_id else ''}{item.number}: "
                f"{item.title} (ID: {item.id}) [{item.status}]"
                for item in sessions
            )
        )

    @commands.command(name="read-session")
    async def read_session(
        self, ctx: commands.Context, *, identifier: str
    ) -> None:
        """Display session details from the current campaign."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign_id = self.store.current(guild_id).id
            session = self.sessions.find(identifier, campaign_id)
        except (CampaignError, SessionError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"ID: {session.id}\nCampaign ID: {session.campaign_id}\n"
            f"Number: {session.number}\nTitle: {session.title}\n"
            f"Description: {session.description or '(none)'}\n"
            f"Status: {session.status}\nCreated at: {session.created_at}\n"
            f"Played at: {session.played_at}\n"
            f"Ended at: {session.ended_at or '(ongoing)'}"
        )

    @commands.command(name="update-session")
    async def update_session(
        self,
        ctx: commands.Context,
        identifier: str,
        title: str | None = None,
        *,
        description: str | None = None,
        played_at: str | None = None,
    ) -> None:
        """Update session metadata."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.update(
                guild_id, identifier, title, description, played_at
            )
        except (SessionError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Session updated: **{session.title}** "
            f"(ID: {session.id}, number: {session.number})."
        )

    @commands.command(name="end-session")
    async def end_session(self, ctx: commands.Context) -> None:
        """End the current session."""
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.end_current(guild_id)
        except SessionError as error:
            await ctx.send(str(error))
            return
        await ctx.send(f"Session **{session.title}** ended.")


class JournalBot(commands.Bot):
    """Minimal Discord bot for the JournalBot application."""

    _ready_announcement_sent: bool = False

    def __init__(
        self, *args: Any, database_path: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.campaigns = CampaignStore(database_path or get_database_path())

    async def setup_hook(self) -> None:
        """Run one-time asynchronous setup before the bot connects."""
        await self.add_cog(CampaignCommands(self.campaigns))
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

    async def on_command(self, context: commands.Context) -> None:
        """Log campaign and session command invocations with their user."""
        command = context.command
        if command is None or command.qualified_name not in LOGGED_COMMANDS:
            return

        author = context.author
        message = context.message
        command_text = message.content
        LOGGER.info(
            "command_invoked timestamp=%s user=%s user_id=%s command=%s",
            datetime.now(timezone.utc).isoformat(),
            getattr(author, "name", str(author)),
            getattr(author, "id", "unknown"),
            command_text,
        )

    async def on_command_error(
        self, context: commands.Context, error: commands.CommandError
    ) -> None:
        """Explain missing required command parameters to the user."""
        if isinstance(error, commands.MissingRequiredArgument):
            await context.send(
                f"Missing required parameter: `{error.param.name}`. "
                "Use `Bot: help` for command usage."
            )
            return
        await super().on_command_error(context, error)

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
