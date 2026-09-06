"""Unit tests for JournalBot Discord event handlers."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from journalbot.bot import (
    COMMANDS_HELP,
    CampaignCommands,
    JournalBot,
    _get_ready_channel_id,
    create_bot,
    parse_named_arguments,
)
from journalbot.campaigns import CampaignStore


def run(coroutine: object) -> object:
    """Run one asynchronous bot callback in an isolated event loop."""
    return asyncio.run(coroutine)  # type: ignore[arg-type]


@pytest.fixture
def bot() -> JournalBot:
    """Create a bot instance without connecting it to Discord."""
    return create_bot()


@pytest.fixture
def user_message() -> MagicMock:
    """Create a non-bot Discord message test double."""
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.channel.send = AsyncMock()
    return message


def test_create_bot_configures_message_content_intent(bot: JournalBot) -> None:
    """
    The text-command handler receives message content. This exercises the `create bot
    configures message content intent` scenario and asserts the expected observable
    result or error.
    """
    assert bot.command_prefix == "!"
    assert bot.intents.message_content is True


def test_named_arguments_support_assignment_and_double_dash_forms() -> None:
    """
    Named command options accept both supported syntaxes. This exercises the `named
    arguments support assignment and double dash forms` scenario and asserts the
    expected observable result or error.
    """
    assert parse_named_arguments(
        'title="Zrób Bota" description="Przygotuj bota" giver="Khel"'
    ) == {
        "title": "Zrób Bota",
        "description": "Przygotuj bota",
        "giver": "Khel",
    }
    assert parse_named_arguments(
        '--title "Zrób Bota" --description "Przygotuj bota" --giver "Khel"'
    ) == {
        "title": "Zrób Bota",
        "description": "Przygotuj bota",
        "giver": "Khel",
    }
    assert parse_named_arguments(
        '"Zrób Bota" description="Przygotuj bota"',
        positional_identifier=True,
    ) == {
        "identifier": "Zrób Bota",
        "description": "Przygotuj bota",
    }


def test_describe_message_returns_bot_purpose(
    bot: JournalBot, user_message: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The describe trigger sends the bot description. This exercises the `describe message
    returns bot purpose` scenario and asserts the expected observable result or error.
    """
    user_message.content = "Bot: describe"
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_awaited_once_with(
        "I am JournalBot, a Discord bot for keeping a structured journal "
        "for Pathfinder 2e campaigns."
    )
    process_commands.assert_awaited_once_with(user_message)


@pytest.mark.parametrize("content", ["Bot: help", "Bot: commands"])
def test_help_aliases_list_available_commands(
    bot: JournalBot,
    user_message: MagicMock,
    content: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Both help triggers send the same command list. This exercises the `help aliases list
    available commands` scenario and asserts the expected observable result or error.
    """
    user_message.content = content
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_awaited_once_with(COMMANDS_HELP)


def test_bot_messages_are_ignored(
    bot: JournalBot, user_message: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The bot does not respond to messages sent by bots. This exercises the `bot messages
    are ignored` scenario and asserts the expected observable result or error.
    """
    user_message.author.bot = True
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_not_awaited()
    process_commands.assert_not_awaited()


def test_other_messages_do_not_send_a_response(
    bot: JournalBot, user_message: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Unrecognised messages are passed to the command processor only. This exercises the
    `other messages do not send a response` scenario and asserts the expected observable
    result or error.
    """
    user_message.content = "Hello, JournalBot"
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_not_awaited()
    process_commands.assert_awaited_once_with(user_message)


@pytest.mark.parametrize("command_name", ["start-campaign", "end-session"])
def test_campaign_and_session_commands_are_logged(
    bot: JournalBot,
    command_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Lifecycle command invocations include timestamp, user, and text. This exercises the
    `campaign and session commands are logged` scenario and asserts the expected
    observable result or error.
    """
    context = SimpleNamespace(
        command=SimpleNamespace(qualified_name=command_name),
        author=SimpleNamespace(name="Tomek", id=42),
        message=SimpleNamespace(content=f"!{command_name} details"),
    )

    with caplog.at_level("INFO", logger="journalbot.bot"):
        run(bot.on_command(cast(Any, context)))

    assert "command_invoked" in caplog.text
    assert "user=Tomek" in caplog.text
    assert "user_id=42" in caplog.text
    assert f"command=!{command_name} details" in caplog.text
    assert "timestamp=" in caplog.text


def test_unrelated_commands_are_not_logged(
    bot: JournalBot, caplog: pytest.LogCaptureFixture
) -> None:
    """
    Only campaign and session commands use the invocation audit log. This exercises the
    `unrelated commands are not logged` scenario and asserts the expected observable
    result or error.
    """
    context = SimpleNamespace(
        command=SimpleNamespace(qualified_name="help"),
        author=SimpleNamespace(name="Tomek", id=42),
        message=SimpleNamespace(content="!help"),
    )

    with caplog.at_level("INFO", logger="journalbot.bot"):
        run(bot.on_command(cast(Any, context)))

    assert "command_invoked" not in caplog.text


def test_missing_required_parameter_explains_how_to_get_help(
    bot: JournalBot,
) -> None:
    """
    Missing command arguments produce actionable user-facing guidance. This exercises
    the `missing required parameter explains how to get help` scenario and asserts the
    expected observable result or error.
    """
    context = MagicMock()
    context.send = AsyncMock()
    error = commands.MissingRequiredArgument(
        cast(Any, SimpleNamespace(name="title", displayed_name="title"))
    )

    run(bot.on_command_error(context, error))

    context.send.assert_awaited_once_with(
        "Missing required parameter: `title`. "
        "Use `Bot: help` for command usage."
    )


def test_ready_does_not_fetch_a_channel_without_configuration(
    bot: JournalBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A ready announcement is optional. This exercises the `ready does not fetch a channel
    without configuration` scenario and asserts the expected observable result or error.
    """
    monkeypatch.delenv("DISCORD_READY_CHANNEL_ID", raising=False)
    fetch_channel = AsyncMock()
    monkeypatch.setattr(bot, "fetch_channel", fetch_channel)

    run(bot.on_ready())

    fetch_channel.assert_not_awaited()
    assert bot._ready_announcement_sent is False


def test_ready_announces_once_to_configured_messageable_channel(
    bot: JournalBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The configured channel receives one ready announcement. This exercises the `ready
    announces once to configured messageable channel` scenario and asserts the expected
    observable result or error.
    """

    class FakeMessageable:
        def __init__(self) -> None:
            self.send = AsyncMock()

    channel = FakeMessageable()
    monkeypatch.setenv("DISCORD_READY_CHANNEL_ID", "123")
    fetch_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr(bot, "fetch_channel", fetch_channel)

    with patch("journalbot.bot.discord.abc.Messageable", FakeMessageable):
        run(bot.on_ready())
        run(bot.on_ready())

    fetch_channel.assert_awaited_once_with(123)
    channel.send.assert_awaited_once_with("Ready to rumble")
    assert bot._ready_announcement_sent is True


def test_ready_does_not_send_to_non_messageable_channel(
    bot: JournalBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A non-messageable configured channel leaves the announcement pending. This exercises
    the `ready does not send to non messageable channel` scenario and asserts the
    expected observable result or error.
    """
    monkeypatch.setenv("DISCORD_READY_CHANNEL_ID", "123")
    monkeypatch.setattr(bot, "fetch_channel", AsyncMock(return_value=object()))

    run(bot.on_ready())

    assert bot._ready_announcement_sent is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("951928146700140604", 951928146700140604)],
)
def test_get_ready_channel_id_returns_optional_numeric_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: int | None
) -> None:
    """
    Ready channel configuration is optional and numeric. This exercises the `get ready
    channel id returns optional numeric value` scenario and asserts the expected
    observable result or error.
    """
    if value is None:
        monkeypatch.delenv("DISCORD_READY_CHANNEL_ID", raising=False)
    else:
        monkeypatch.setenv("DISCORD_READY_CHANNEL_ID", value)

    assert _get_ready_channel_id() == expected


def test_get_ready_channel_id_rejects_non_numeric_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """
    Invalid channel IDs do not prevent startup. This exercises the `get ready channel id
    rejects non numeric value` scenario and asserts the expected observable result or
    error.
    """
    monkeypatch.setenv("DISCORD_READY_CHANNEL_ID", "not-a-channel-id")

    assert _get_ready_channel_id() is None
    assert "must be a numeric Discord channel ID" in caplog.text


def test_campaign_commands_cover_lifecycle_and_guild_context(tmp_path) -> None:
    """
    Campaign commands expose the persistent lifecycle and guild selection. This
    exercises the `campaign commands cover lifecycle and guild context` scenario and
    asserts the expected observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog,
            ctx,
            arguments='title="Kingmaker" description="Stolen land"',
        )
    )
    campaign = cog.store.current(123)
    assert campaign.title == "Kingmaker"
    ctx.send.assert_awaited_once_with(
        f"Campaign **Kingmaker** created and selected (ID: {campaign.id})."
    )

    ctx.send.reset_mock()
    run(
        cast(Any, cog.read_campaign.callback)(
            cog, ctx, arguments=str(campaign.id)
        )
    )
    read_response = ctx.send.await_args.args[0]
    assert f"ID: {campaign.id}" in read_response
    assert "Title: Kingmaker" in read_response
    assert "Description: Stolen land" in read_response
    assert "Status: ACTIVE" in read_response

    ctx.send.reset_mock()
    run(
        cast(Any, cog.update_campaign.callback)(
            cog,
            ctx,
            arguments=(
                f'{campaign.id} title="New Kingmaker" '
                'description="Updated"'
            ),
        )
    )
    updated = cog.store.find(str(campaign.id))
    assert updated.id == campaign.id
    assert updated.title == "New Kingmaker"
    assert updated.description == "Updated"

    ctx.send.reset_mock()
    run(cast(Any, cog.end_campaign.callback)(cog, ctx))
    assert cog.store.current(123).status == "ENDED"
    ctx.send.assert_awaited_once_with("Campaign **New Kingmaker** ended.")

    ctx.send.reset_mock()
    run(
        cast(Any, cog.use_campaign.callback)(
            cog, ctx, arguments=str(campaign.id)
        )
    )
    ctx.send.assert_awaited_once_with(
        f"Selected campaign **New Kingmaker** (ID: {campaign.id})."
    )


def test_session_commands_cover_lifecycle_and_context(tmp_path) -> None:
    """
    Session commands expose creation, inspection, updates, and ending. This exercises
    the `session commands cover lifecycle and context` scenario and asserts the expected
    observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog,
            ctx,
            arguments='title="Kingmaker" description="Stolen land"',
        )
    )
    ctx.send.reset_mock()
    run(
        cast(Any, cog.start_session.callback)(
            cog,
            ctx,
            arguments='title="Opening" description="The party arrives"',
        )
    )
    session = cog.sessions.current(123)
    ctx.send.assert_awaited_once_with(
        f"Session **Opening** created and selected "
        f"(ID: {session.id}, number: {session.number})."
    )

    ctx.send.reset_mock()
    run(cast(Any, cog.list_session.callback)(cog, ctx))
    assert f"* 1: Opening (ID: {session.id}) [ACTIVE]" in (
        ctx.send.await_args.args[0]
    )

    ctx.send.reset_mock()
    run(
        cast(Any, cog.read_session.callback)(
            cog, ctx, arguments=str(session.id)
        )
    )
    read_response = ctx.send.await_args.args[0]
    assert f"ID: {session.id}" in read_response
    assert "Title: Opening" in read_response
    assert "Description: The party arrives" in read_response
    assert "Status: ACTIVE" in read_response

    ctx.send.reset_mock()
    run(
        cast(Any, cog.add_journal_event.callback)(
            cog,
            ctx,
            arguments='description="The party discovered an ancient shrine."',
        )
    )
    assert "Journal event added to Session #1." in ctx.send.await_args.args[0]

    ctx.send.reset_mock()
    run(
        cast(Any, cog.read_session.callback)(
            cog, ctx, arguments=str(session.id)
        )
    )
    read_response = ctx.send.await_args.args[0]
    assert "Journal events:" in read_response
    assert "The party discovered an ancient shrine." in read_response

    ctx.send.reset_mock()
    run(
        cast(Any, cog.update_session.callback)(
            cog,
            ctx,
            arguments=(
                f'{session.id} title="Revised opening" '
                'description="Updated notes" '
                'played_at="2026-09-05T18:00:00+00:00"'
            ),
        )
    )
    updated = cog.sessions.find(str(session.id), session.campaign_id)
    assert updated.title == "Revised opening"
    assert updated.description == "Updated notes"
    assert updated.played_at == "2026-09-05T18:00:00+00:00"

    ctx.send.reset_mock()
    run(cast(Any, cog.end_session.callback)(cog, ctx))
    ended = cog.sessions.current(123)
    assert ended.status == "ENDED"
    ctx.send.assert_awaited_once_with("Session **Revised opening** ended.")

    ctx.send.reset_mock()
    run(
        cast(Any, cog.use_session.callback)(
            cog, ctx, arguments='"Revised opening"'
        )
    )
    ctx.send.assert_awaited_once_with(
        f"Selected session **Revised opening** "
        f"(ID: {session.id}, number: {session.number})."
    )


def test_read_session_displays_events_for_requested_session(tmp_path) -> None:
    """Reading an older session must not display events from the current session."""
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog, ctx, arguments='title="Kingmaker"'
        )
    )
    run(
        cast(Any, cog.start_session.callback)(
            cog, ctx, arguments='title="Opening"'
        )
    )
    first_session = cog.sessions.current(123)
    run(
        cast(Any, cog.add_journal_event.callback)(
            cog, ctx, arguments='description="Opening event"'
        )
    )
    run(cast(Any, cog.end_session.callback)(cog, ctx))
    run(
        cast(Any, cog.start_session.callback)(
            cog, ctx, arguments='title="Investigation"'
        )
    )
    run(
        cast(Any, cog.add_journal_event.callback)(
            cog, ctx, arguments='description="Investigation event"'
        )
    )

    ctx.send.reset_mock()
    run(
        cast(Any, cog.read_session.callback)(
            cog, ctx, arguments=str(first_session.id)
        )
    )

    response = ctx.send.await_args.args[0]
    assert "Opening event" in response
    assert "Investigation event" not in response


def test_campaign_commands_reject_direct_messages(tmp_path) -> None:
    """
    Campaign lifecycle commands require a Discord guild context. This exercises the
    `campaign commands reject direct messages` scenario and asserts the expected
    observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = None
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog, ctx, arguments='title="Kingmaker"'
        )
    )

    ctx.send.assert_awaited_once_with(
        "Campaign commands can only be used in a Discord server."
    )


def test_quest_creation_accepts_both_named_argument_forms(tmp_path) -> None:
    """
    Quest creation keeps values with spaces in either supported syntax. This exercises
    the `quest creation accepts both named argument forms` scenario and asserts the
    expected observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog, ctx, arguments='--title "Kingmaker" --description "Stolen land"'
        )
    )
    run(
        cast(Any, cog.start_session.callback)(
            cog, ctx, arguments='title="Opening"'
        )
    )

    run(
        cast(Any, cog.create_quest.callback)(
            cog,
            ctx,
            arguments=(
                'title="Zrób Bota" '
                'description="Przygotuj bota do dziennika" '
                'quest_giver="Khel" received_at_location="Domek"'
            ),
        )
    )
    run(
        cast(Any, cog.create_quest.callback)(
            cog,
            ctx,
            arguments=(
                '--title "Zrób Drugiego Bota" '
                '--description "Drugi opis" '
                '--quest-giver "Khel" '
                '--received-at-location "Domek"'
            ),
        )
    )

    quests = cog.quests.list(123)
    assert [quest.title for quest in quests] == [
        "Zrób Bota",
        "Zrób Drugiego Bota",
    ]
    assert quests[0].description == "Przygotuj bota do dziennika"
    assert quests[1].quest_giver == "Khel"


def test_quest_commands_cover_details_listing_and_state_transitions(
    tmp_path,
) -> None:
    """
    Quest commands expose metadata, filters, and lifecycle transitions. This exercises
    the `quest commands cover details listing and state transitions` scenario and
    asserts the expected observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog, ctx, arguments='title="Kingmaker"'
        )
    )
    run(
        cast(Any, cog.start_session.callback)(
            cog, ctx, arguments='title="Opening"'
        )
    )

    run(
        cast(Any, cog.create_quest.callback)(
            cog,
            ctx,
            arguments=(
                'title="Find the Merchant" '
                'description="Find the missing merchant." '
                'quest_giver="Mayor Menhemes" '
                'received_at_location="Otari"'
            ),
        )
    )
    quest_id = cog.quests.list(123)[0].id

    ctx.send.reset_mock()
    run(
        cast(Any, cog.progress_quest.callback)(
            cog,
            ctx,
            arguments=(
                f'{quest_id} description="Found tracks toward the abandoned mine."'
            ),
        )
    )
    response = ctx.send.await_args.args[0]
    assert "Quest: Find the Merchant" in response
    assert "Session: #1" in response
    assert 'Progress added:\n"Found tracks toward the abandoned mine."' in response

    ctx.send.reset_mock()
    run(
        cast(Any, cog.quest_details.callback)(
            cog, ctx, arguments=str(quest_id)
        )
    )
    response = ctx.send.await_args.args[0]
    assert f"ID: {quest_id}" in response
    assert "Title: Find the Merchant" in response
    assert "Status: ACTIVE" in response
    assert "Quest giver: Mayor Menhemes" in response
    assert "Received at location: Otari" in response
    assert "Description: Find the missing merchant." in response
    assert "Progress history:" in response
    assert "Session #1: Found tracks toward the abandoned mine." in response

    ctx.send.reset_mock()
    run(
        cast(Any, cog.update_quest.callback)(
            cog,
            ctx,
            arguments=(
                f'{quest_id} title="Find the Missing Merchant" '
                'quest_giver="" received_at_location=""'
            ),
        )
    )
    updated = cog.quests.find(str(quest_id), cog.store.current(123).id)
    assert updated.title == "Find the Missing Merchant"
    assert updated.quest_giver is None
    assert updated.received_at_location is None

    ctx.send.reset_mock()
    run(
        cast(Any, cog.create_quest.callback)(
            cog,
            ctx,
            arguments='title="Escort the Merchant" description="Bring him home."',
        )
    )
    second_id = cog.quests.list(123)[1].id

    run(
        cast(Any, cog.complete_quest.callback)(
            cog, ctx, arguments=str(quest_id)
        )
    )
    run(
        cast(Any, cog.fail_quest.callback)(
            cog, ctx, arguments=str(second_id)
        )
    )

    ctx.send.reset_mock()
    run(cast(Any, cog.list_quests.callback)(cog, ctx, arguments='status="all"'))
    assert "Find the Missing Merchant" in ctx.send.await_args.args[0]
    assert "Escort the Merchant" in ctx.send.await_args.args[0]

    ctx.send.reset_mock()
    run(
        cast(Any, cog.list_quests.callback)(
            cog, ctx, arguments='status="completed"'
        )
    )
    assert "Find the Missing Merchant" in ctx.send.await_args.args[0]
    assert "FAILED" not in ctx.send.await_args.args[0]

    ctx.send.reset_mock()
    run(
        cast(Any, cog.list_quests.callback)(
            cog, ctx, arguments='status="failed"'
        )
    )
    assert "Escort the Merchant" in ctx.send.await_args.args[0]


@pytest.mark.parametrize(
    "arguments",
    [
        "--title",
        "--title --description value",
        "--title description=value",
        "1title=value",
        "title=value title=other",
        "title=value unexpected",
    ],
)
def test_named_argument_parser_rejects_malformed_input(arguments: str) -> None:
    """
    Malformed named arguments are rejected instead of being guessed. This exercises the
    `named argument parser rejects malformed input` scenario and asserts the expected
    observable result or error.
    """
    with pytest.raises(ValueError):
        parse_named_arguments(arguments)


def test_named_argument_parser_rejects_nonleading_identifier() -> None:
    """
    An identifier cannot be supplied as a named option. This exercises the `named
    argument parser rejects nonleading identifier` scenario and asserts the expected
    observable result or error.
    """
    with pytest.raises(ValueError, match="identifier must be the first"):
        parse_named_arguments(
            "title=value identifier=42", positional_identifier=True
        )


@pytest.mark.parametrize(
    ("command", "arguments", "message"),
    [
        ("start_campaign", "", "Missing required parameter: `title`."),
        ("start_session", "unexpected", "Unexpected argument"),
        (
            "create_quest",
            'title="Only title"',
            "Missing required parameter: `description`.",
        ),
        ("update_quest", "", "Missing required parameter: `identifier`."),
    ],
)
def test_command_validation_reports_usage_errors(
    tmp_path, command: str, arguments: str, message: str
) -> None:
    """
    Command validation failures are reported to the user. This exercises the `command
    validation reports usage errors` scenario and asserts the expected observable result
    or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, getattr(cog, command).callback)(
            cog, ctx, arguments=arguments
        )
    )

    assert message in ctx.send.await_args.args[0]


@pytest.mark.parametrize(
    "command",
    [
        "start_campaign",
        "use_campaign",
        "end_campaign",
        "start_session",
        "use_session",
        "list_session",
        "read_session",
        "update_session",
        "end_session",
        "create_quest",
        "update_quest",
        "quest_details",
        "list_quests",
        "complete_quest",
        "fail_quest",
        "progress_quest",
        "add_journal_event",
    ],
)
def test_all_commands_reject_direct_messages(tmp_path, command: str) -> None:
    """
    Every guild-scoped command rejects direct-message contexts. This exercises the `all
    commands reject direct messages` scenario and asserts the expected observable result
    or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = None
    ctx.send = AsyncMock()

    arguments = {
        "start_campaign": 'title="Kingmaker"',
        "use_campaign": "1",
        "list_campaign": "",
        "read_campaign": "1",
        "update_campaign": "1 title=Updated",
        "end_campaign": "",
        "start_session": "",
        "use_session": "1",
        "list_session": "",
        "read_session": "1",
        "update_session": "1 title=Updated",
        "end_session": "",
        "create_quest": 'title=Quest description=Description',
        "update_quest": "1 title=Updated",
        "quest_details": "1",
        "list_quests": "",
        "complete_quest": "1",
        "fail_quest": "1",
        "progress_quest": "1 description=Progress",
        "add_journal_event": 'description="Session event"',
    }[command]

    run(
        cast(Any, getattr(cog, command).callback)(
            cog, ctx, arguments=arguments
        )
    )

    ctx.send.assert_awaited_once_with(
        "Campaign commands can only be used in a Discord server."
    )


def test_quest_commands_report_missing_context_and_not_found_errors(tmp_path) -> None:
    """
    Quest commands report missing context and unknown identifiers clearly. This
    exercises the `quest commands report missing context and not found errors` scenario
    and asserts the expected observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.create_quest.callback)(
            cog,
            ctx,
            arguments='title="Quest" description="Description"',
        )
    )
    assert "No campaign is currently selected" in ctx.send.await_args.args[0]

    run(
        cast(Any, cog.start_campaign.callback)(
            cog, ctx, arguments='title="Kingmaker"'
        )
    )
    ctx.send.reset_mock()
    run(
        cast(Any, cog.create_quest.callback)(
            cog,
            ctx,
            arguments='title="Quest" description="Description"',
        )
    )
    assert "No session is currently selected" in ctx.send.await_args.args[0]

    ctx.send.reset_mock()
    for command in ("quest_details", "complete_quest", "fail_quest"):
        run(
            cast(Any, getattr(cog, command).callback)(
                cog, ctx, arguments="999"
            )
        )
        assert "was not found" in ctx.send.await_args.args[0]
        ctx.send.reset_mock()


def test_list_quests_reports_empty_filtered_results(tmp_path) -> None:
    """
    A valid filter with no matching quests produces an explicit response. This exercises
    the `list quests reports empty filtered results` scenario and asserts the expected
    observable result or error.
    """
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(
        cast(Any, cog.start_campaign.callback)(
            cog, ctx, arguments='title="Kingmaker"'
        )
    )
    ctx.send.reset_mock()
    run(
        cast(Any, cog.list_quests.callback)(
            cog, ctx, arguments='status="unknown"'
        )
    )
    assert "Unknown quest status filter" in ctx.send.await_args.args[0]

    ctx.send.reset_mock()
    run(
        cast(Any, cog.list_quests.callback)(
            cog, ctx, arguments='status="completed"'
        )
    )

    assert ctx.send.await_args.args[0] == (
        "No quests found for the current campaign (completed)."
    )
