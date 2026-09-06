"""Discord bot construction and event handlers."""

import logging
import os
import re
import shlex
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
from journalbot.quests import QuestError, QuestStore
from journalbot.sessions import SessionError, SessionStore

LOGGER = logging.getLogger(__name__)


class CommandArgumentsError(ValueError):
    """Raised when named command arguments cannot be parsed."""


def parse_named_arguments(
    arguments: str, *, positional_identifier: bool = False
) -> dict[str, str]:
    """Parse named arguments with an optional first positional identifier."""
    tokens = shlex.split(arguments, posix=True)
    parsed: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            positional_identifier
            and index == 0
            and not token.startswith("--")
            and "=" not in token
        ):
            parsed["identifier"] = token
            index += 1
            continue
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                key, value = key.split("=", 1)
            else:
                index += 1
                if index >= len(tokens) or (
                    tokens[index].startswith("--")
                    or re.fullmatch(r"[a-z][a-z0-9_-]*=.*", tokens[index])
                ):
                    raise CommandArgumentsError(
                        f"Parameter `{key}` requires a value."
                    )
                value = tokens[index]
        elif "=" in token:
            key, value = token.split("=", 1)
        else:
            raise CommandArgumentsError(
                f"Unexpected argument `{token}`. Use named parameters."
            )

        key = key.strip().lower().replace("-", "_")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise CommandArgumentsError(f"Invalid parameter name `{key}`.")
        if positional_identifier and key == "identifier":
            raise CommandArgumentsError(
                "The identifier must be the first positional argument."
            )
        if key in parsed:
            raise CommandArgumentsError(f"Parameter `{key}` was provided twice.")
        parsed[key] = value
        index += 1
    return parsed


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
        "create-quest",
        "update-quest",
        "quest-details",
        "list-quests",
        "complete-quest",
        "fail-quest",
        "progress-quest",
    }
)

COMMANDS_HELP = "\n".join(
    (
        "Available commands:",
        "- `Bot: describe` — describe JournalBot's purpose.",
        "- `Bot: help` or `Bot: commands` — show this command list.",
        "- `!start-campaign title=\"...\" [description=\"...\"]` — create a campaign.",
        "- `!use-campaign <identifier>` — select a campaign.",
        "- `!list-campaign` — list campaigns.",
        "- `!read-campaign <identifier>` — show campaign details.",
        "- `!update-campaign <identifier> [title=\"...\"] "
        "[description=\"...\"]` — update metadata.",
        "- `!end-campaign` — end the selected campaign.",
        "- `!start-session [title=\"...\"] [description=\"...\"]` — create a session.",
        "- `!use-session <identifier>` — select a session.",
        "- `!list-session` — list sessions for the current campaign.",
        "- `!read-session <identifier>` — show session details.",
        "- `!update-session <identifier> [title=\"...\"] "
        "[description=\"...\"] [played_at=\"...\"]` — "
        "update session metadata.",
        "- `!end-session` — end the selected session.",
        "- `!create-quest title=\"...\" description=\"...\" "
        "[quest_giver=\"...\"] [received_at_location=\"...\"]` — create a quest.",
        "- `!update-quest <identifier> [title=\"...\"] "
        "[description=\"...\"] [quest_giver=\"...\"] "
        "[received_at_location=\"...\"]` — update quest metadata.",
        "- `!quest-details <identifier>` — show quest details.",
        "- `!list-quests [status=\"all|active|completed|failed|finished\"]` — "
        "list quests.",
        "- `!complete-quest <identifier>` — complete a quest.",
        "- `!fail-quest <identifier>` — fail a quest.",
        "- `!progress-quest <identifier> description=\"...\"` — add quest progress.",
        "Named options also support `--key \"value\"`, for example "
        "`!create-quest --title \"Find the merchant\" --description \"...\"`.",
    )
)


class CampaignCommands(commands.Cog):
    """Discord commands for campaign lifecycle and guild context."""

    def __init__(self, store: CampaignStore) -> None:
        self.store = store
        self.sessions = SessionStore(store.database_path)
        self.quests = QuestStore(store.database_path)

    async def _require_guild(self, ctx: commands.Context) -> int | None:
        if ctx.guild is None:
            await ctx.send("Campaign commands can only be used in a Discord server.")
            return None
        return ctx.guild.id

    async def _parse_arguments(
        self,
        ctx: commands.Context,
        arguments: str,
        allowed: set[str],
        required: set[str] | None = None,
        positional_identifier: bool = False,
    ) -> dict[str, str] | None:
        """Parse and validate one command's named arguments."""
        try:
            parsed = parse_named_arguments(
                arguments, positional_identifier=positional_identifier
            )
        except (CommandArgumentsError, ValueError) as error:
            await ctx.send(f"{error} Use `Bot: help` for command usage.")
            return None

        unknown = sorted(set(parsed) - allowed)
        if unknown:
            names = ", ".join(f"`{name}`" for name in unknown)
            await ctx.send(
                f"Unknown parameter(s): {names}. "
                "Use `Bot: help` for command usage."
            )
            return None

        for name in required or set():
            if name not in parsed or not parsed[name].strip():
                await ctx.send(
                    f"Missing required parameter: `{name}`. "
                    "Use `Bot: help` for command usage."
                )
                return None
        return parsed

    @commands.command(name="start-campaign")
    async def start_campaign(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Create and select a campaign."""
        options = await self._parse_arguments(
            ctx, arguments, {"title", "description"}, {"title"}
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign = self.store.create(
                guild_id, options["title"], options.get("description", "")
            )
        except (CampaignError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Campaign **{campaign.title}** created and selected "
            f"(ID: {campaign.id})."
        )

    @commands.command(name="use-campaign")
    async def use_campaign(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Select a campaign by ID or exact title."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign = self.store.select(guild_id, options["identifier"])
        except CampaignError as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Selected campaign **{campaign.title}** (ID: {campaign.id})."
        )

    @commands.command(name="list-campaign")
    async def list_campaign(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """List all campaigns."""
        if await self._parse_arguments(ctx, arguments, set()) is None:
            return
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
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Display campaign details."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        try:
            campaign = self.store.find(options["identifier"])
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
        *,
        arguments: str = "",
    ) -> None:
        """Update campaign title and/or description."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier", "title", "description"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        try:
            campaign = self.store.update(
                options["identifier"],
                options.get("title"),
                options.get("description"),
            )
        except (CampaignError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Campaign updated: **{campaign.title}** (ID: {campaign.id})."
        )

    @commands.command(name="end-campaign")
    async def end_campaign(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """End the current campaign."""
        if await self._parse_arguments(ctx, arguments, set()) is None:
            return
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
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Create and select a session for the current campaign."""
        options = await self._parse_arguments(
            ctx, arguments, {"title", "description"}
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.create(
                guild_id, options.get("title"), options.get("description", "")
            )
        except (CampaignError, SessionError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Session **{session.title}** created and selected "
            f"(ID: {session.id}, number: {session.number})."
        )

    @commands.command(name="use-session")
    async def use_session(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Select a session by ID or exact title."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.select(guild_id, options["identifier"])
        except SessionError as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Selected session **{session.title}** "
            f"(ID: {session.id}, number: {session.number})."
        )

    @commands.command(name="list-session")
    async def list_session(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """List sessions for the current campaign."""
        if await self._parse_arguments(ctx, arguments, set()) is None:
            return
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
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Display session details from the current campaign."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign_id = self.store.current(guild_id).id
            session = self.sessions.find(options["identifier"], campaign_id)
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
        *,
        arguments: str = "",
    ) -> None:
        """Update session metadata."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier", "title", "description", "played_at"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.update(
                guild_id,
                options["identifier"],
                options.get("title"),
                options.get("description"),
                options.get("played_at"),
            )
        except (SessionError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Session updated: **{session.title}** "
            f"(ID: {session.id}, number: {session.number})."
        )

    @commands.command(name="end-session")
    async def end_session(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """End the current session."""
        if await self._parse_arguments(ctx, arguments, set()) is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            session = self.sessions.end_current(guild_id)
        except SessionError as error:
            await ctx.send(str(error))
            return
        await ctx.send(f"Session **{session.title}** ended.")

    @commands.command(name="create-quest")
    async def create_quest(
        self,
        ctx: commands.Context,
        *,
        arguments: str = "",
    ) -> None:
        """Create a quest for the current campaign and session."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"title", "description", "quest_giver", "received_at_location"},
            {"title", "description"},
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            quest = self.quests.create(
                guild_id,
                options["title"],
                options.get("description"),
                options.get("quest_giver"),
                options.get("received_at_location"),
            )
        except (CampaignError, QuestError, SessionError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(
            f"Quest **{quest.title}** created and started in session "
            f"{quest.started_session_id} (ID: {quest.id})."
        )

    @commands.command(name="update-quest")
    async def update_quest(
        self,
        ctx: commands.Context,
        *,
        arguments: str = "",
    ) -> None:
        """Update quest metadata without changing its identity."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {
                "identifier",
                "title",
                "description",
                "quest_giver",
                "received_at_location",
            },
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            quest = self.quests.update(
                guild_id,
                options["identifier"],
                options.get("title"),
                options.get("description"),
                options.get("quest_giver"),
                options.get("received_at_location"),
            )
        except (CampaignError, QuestError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(f"Quest updated: **{quest.title}** (ID: {quest.id}).")

    @commands.command(name="quest-details")
    async def quest_details(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Display detailed quest information."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            campaign_id = self.store.current(guild_id).id
            quest = self.quests.find(options["identifier"], campaign_id)
        except (CampaignError, QuestError, SessionError) as error:
            await ctx.send(str(error))
            return
        progress_history = self.quests.list_progress(guild_id, options["identifier"])
        lines = [
            f"ID: {quest.id}\nCampaign ID: {quest.campaign_id}\n"
            f"Title: {quest.title}\nStatus: {quest.status}\n"
            f"Quest giver: {quest.quest_giver or '(none)'}\n"
            f"Received at location: {quest.received_at_location or '(none)'}\n"
            f"Started in session: {quest.started_session_id}\n"
            f"Description: {quest.description or '(none)'}\n"
            f"Closed at: {quest.closed_at or '(ongoing)'}"
        ]
        if progress_history:
            items = []
            for entry in progress_history:
                try:
                    session = self.sessions.find(
                        str(entry.session_id), quest.campaign_id
                    )
                    label = f"Session #{session.number}"
                except SessionError:
                    label = f"Session {entry.session_id}"
                items.append(f"{label}: {entry.description}")
            lines.append("\nProgress history:\n" + "\n".join(items))
        await ctx.send("".join(lines))

    @commands.command(name="list-quests")
    async def list_quests(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """List quests for the current campaign by lifecycle state."""
        options = await self._parse_arguments(ctx, arguments, {"status"})
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            status = options.get("status", "all")
            quests = self.quests.list(guild_id, status)
        except (CampaignError, QuestError, ValueError) as error:
            await ctx.send(str(error))
            return
        if not quests:
            await ctx.send(f"No quests found for the current campaign ({status}).")
            return
        await ctx.send(
            "\n".join(
                f"{item.id}: {item.title} [{item.status}]" for item in quests
            )
        )

    @commands.command(name="complete-quest")
    async def complete_quest(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Mark a quest as completed."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            quest = self.quests.complete(guild_id, options["identifier"])
        except (CampaignError, QuestError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(f"Quest **{quest.title}** marked as completed.")

    @commands.command(name="fail-quest")
    async def fail_quest(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Mark a quest as failed."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier"},
            {"identifier"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            quest = self.quests.fail(guild_id, options["identifier"])
        except (CampaignError, QuestError, ValueError) as error:
            await ctx.send(str(error))
            return
        await ctx.send(f"Quest **{quest.title}** marked as failed.")

    @commands.command(name="progress-quest")
    async def progress_quest(
        self, ctx: commands.Context, *, arguments: str = ""
    ) -> None:
        """Add a historical progress entry to the current quest."""
        options = await self._parse_arguments(
            ctx,
            arguments,
            {"identifier", "description"},
            {"identifier", "description"},
            positional_identifier=True,
        )
        if options is None:
            return
        guild_id = await self._require_guild(ctx)
        if guild_id is None:
            return
        try:
            quest = self.quests.find(
                options["identifier"], self.store.current(guild_id).id
            )
            progress_entry = self.quests.add_progress(
                guild_id,
                options["identifier"],
                options["description"],
            )
        except (CampaignError, QuestError, SessionError, ValueError) as error:
            await ctx.send(str(error))
            return
        session = self.sessions.current(guild_id)
        await ctx.send(
            f"Quest: {quest.title}\n"
            f"Session: #{session.number}\n\n"
            f'Progress added:\n"{progress_entry.description}"'
        )


class JournalBot(commands.Bot):
    """Minimal Discord bot for the JournalBot application."""

    _ready_announcement_sent: bool = False

    def __init__(
        self, *args: Any, database_path: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        resolved_path = database_path or get_database_path()
        self.campaigns = CampaignStore(resolved_path)
        self.quests = QuestStore(resolved_path)

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
