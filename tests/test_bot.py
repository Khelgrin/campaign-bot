"""Unit tests for JournalBot Discord event handlers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from journalbot.bot import (
    COMMANDS_HELP,
    CampaignCommands,
    JournalBot,
    _get_ready_channel_id,
    create_bot,
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
    """The text-command handler receives message content."""
    assert bot.command_prefix == "!"
    assert bot.intents.message_content is True


def test_describe_message_returns_bot_purpose(
    bot: JournalBot, user_message: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The describe trigger sends the bot description."""
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
    """Both help triggers send the same command list."""
    user_message.content = content
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_awaited_once_with(COMMANDS_HELP)


def test_bot_messages_are_ignored(
    bot: JournalBot, user_message: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bot does not respond to messages sent by bots."""
    user_message.author.bot = True
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_not_awaited()
    process_commands.assert_not_awaited()


def test_other_messages_do_not_send_a_response(
    bot: JournalBot, user_message: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unrecognised messages are passed to the command processor only."""
    user_message.content = "Hello, JournalBot"
    process_commands = AsyncMock()
    monkeypatch.setattr(bot, "process_commands", process_commands)

    run(bot.on_message(user_message))

    user_message.channel.send.assert_not_awaited()
    process_commands.assert_awaited_once_with(user_message)


def test_ready_does_not_fetch_a_channel_without_configuration(
    bot: JournalBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ready announcement is optional."""
    monkeypatch.delenv("DISCORD_READY_CHANNEL_ID", raising=False)
    fetch_channel = AsyncMock()
    monkeypatch.setattr(bot, "fetch_channel", fetch_channel)

    run(bot.on_ready())

    fetch_channel.assert_not_awaited()
    assert bot._ready_announcement_sent is False


def test_ready_announces_once_to_configured_messageable_channel(
    bot: JournalBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configured channel receives one ready announcement."""

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
    """A non-messageable configured channel leaves the announcement pending."""
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
    """Ready channel configuration is optional and numeric."""
    if value is None:
        monkeypatch.delenv("DISCORD_READY_CHANNEL_ID", raising=False)
    else:
        monkeypatch.setenv("DISCORD_READY_CHANNEL_ID", value)

    assert _get_ready_channel_id() == expected


def test_get_ready_channel_id_rejects_non_numeric_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid channel IDs do not prevent startup."""
    monkeypatch.setenv("DISCORD_READY_CHANNEL_ID", "not-a-channel-id")

    assert _get_ready_channel_id() is None
    assert "must be a numeric Discord channel ID" in caplog.text


def test_campaign_commands_cover_lifecycle_and_guild_context(tmp_path) -> None:
    """Campaign commands expose the persistent lifecycle and guild selection."""
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    run(cog.start_campaign.callback(cog, ctx, "Kingmaker", description="Stolen land"))
    campaign = cog.store.current(123)
    assert campaign.title == "Kingmaker"
    ctx.send.assert_awaited_once_with(
        f"Campaign **Kingmaker** created and selected (ID: {campaign.id})."
    )

    ctx.send.reset_mock()
    run(cog.read_campaign.callback(cog, ctx, identifier=str(campaign.id)))
    read_response = ctx.send.await_args.args[0]
    assert f"ID: {campaign.id}" in read_response
    assert "Title: Kingmaker" in read_response
    assert "Description: Stolen land" in read_response
    assert "Status: ACTIVE" in read_response

    ctx.send.reset_mock()
    run(
        cog.update_campaign.callback(
            cog, ctx, str(campaign.id), "New Kingmaker", description="Updated"
        )
    )
    updated = cog.store.find(str(campaign.id))
    assert updated.id == campaign.id
    assert updated.title == "New Kingmaker"
    assert updated.description == "Updated"

    ctx.send.reset_mock()
    run(cog.end_campaign.callback(cog, ctx))
    assert cog.store.current(123).status == "ENDED"
    ctx.send.assert_awaited_once_with("Campaign **New Kingmaker** ended.")

    ctx.send.reset_mock()
    run(cog.use_campaign.callback(cog, ctx, identifier=str(campaign.id)))
    ctx.send.assert_awaited_once_with(
        f"Selected campaign **New Kingmaker** (ID: {campaign.id})."
    )


def test_campaign_commands_reject_direct_messages(tmp_path) -> None:
    """Campaign lifecycle commands require a Discord guild context."""
    cog = CampaignCommands(CampaignStore(tmp_path / "journalbot.sqlite3"))
    ctx = MagicMock()
    ctx.guild = None
    ctx.send = AsyncMock()

    run(cog.start_campaign.callback(cog, ctx, "Kingmaker"))

    ctx.send.assert_awaited_once_with(
        "Campaign commands can only be used in a Discord server."
    )
