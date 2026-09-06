"""Tests for the interactive journal renderer and component routing."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from journalbot.bot import CampaignCommands
from journalbot.campaigns import CampaignStore
from journalbot.database import ServerContextModel
from journalbot.journal_ui import JournalRenderer, ProgressModal
from journalbot.quests import QuestStore
from journalbot.sessions import SessionStore


def setup_journal(tmp_path):
    database = tmp_path / "journal.sqlite3"
    campaigns = CampaignStore(database)
    sessions = SessionStore(database)
    quests = QuestStore(database)
    campaigns.create(123, "Kingmaker", "Stolen land")
    session = sessions.create(123, "Opening", "The party arrives")
    quest = quests.create(
        123,
        "Find the Merchant",
        "Find the missing merchant.",
        "Mayor",
        "Otari",
    )
    sessions.create_journal_event(123, "The party found a hidden passage.")
    quests.add_progress(123, str(quest.id), "Tracks lead toward the mine.")
    return (
        JournalRenderer(campaigns, sessions, quests, 123),
        sessions,
        quests,
        session,
        quest,
    )


def test_renderer_builds_dashboard_and_all_navigation_views(tmp_path):
    renderer, _, _, session, quest = setup_journal(tmp_path)

    dashboard = renderer.dashboard()
    assert "Kingmaker" in dashboard.content
    assert "Opening" in dashboard.content
    assert [item.custom_id for item in dashboard.view.children] == [
        "j:q:list:all:0",
        "j:s:list:0",
    ]

    quest_list = renderer.quest_list("all", 0)
    assert "Find the Merchant" in quest_list.content
    assert "j:q:view:" + str(quest.id) in {
        item.custom_id for item in quest_list.view.children
    }
    assert renderer.session_list(0).content.find("Opening") >= 0
    assert "The party found a hidden passage." in renderer.session_details(
        session.id, 0
    ).content
    assert "Tracks lead toward the mine." in renderer.session_details(
        session.id, 0
    ).content


def test_renderer_quest_details_and_confirmation_actions(tmp_path):
    renderer, _, quests, _, quest = setup_journal(tmp_path)
    details = renderer.quest_details(quest.id, "active", 0)
    custom_ids = [item.custom_id for item in details.view.children]
    assert f"j:q:progress:{quest.id}" in custom_ids
    assert f"j:q:complete:{quest.id}:active:0" in custom_ids
    assert f"j:q:fail:{quest.id}:active:0" in custom_ids

    confirmation = renderer._confirmation("q", "complete", quest.id, "active", 0)
    assert f"j:q:confirm-complete:{quest.id}:active:0" in [
        item.custom_id for item in confirmation.view.children
    ]
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.edit_message = AsyncMock()
    confirm_button = confirmation.view.children[0]
    import asyncio

    asyncio.run(confirm_button.callback(interaction))
    assert quests.find(str(quest.id), 1).status == "COMPLETED"
    interaction.response.edit_message.assert_awaited_once()


def test_renderer_routes_navigation_and_progress_modal(tmp_path):
    renderer, _, _, _, quest = setup_journal(tmp_path)
    import asyncio

    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.edit_message = AsyncMock()
    button = renderer.quest_list("all", 0).view.children[-1]
    asyncio.run(button.callback(interaction))
    interaction.response.edit_message.assert_awaited_once()

    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_modal = AsyncMock()
    progress_button = renderer.quest_details(quest.id, "all", 0).view.children[0]
    asyncio.run(progress_button.callback(interaction))
    interaction.response.send_modal.assert_awaited_once()
    assert isinstance(
        interaction.response.send_modal.await_args.args[0], ProgressModal
    )


def test_progress_requires_current_session(tmp_path):
    database = tmp_path / "journal.sqlite3"
    campaigns = CampaignStore(database)
    sessions = SessionStore(database)
    quests = QuestStore(database)
    campaigns.create(123, "Kingmaker", None)
    session = sessions.create(123, "Opening")
    quest = quests.create(123, "Find the Merchant", "Find it.")
    sessions.end_current(123)
    with sessions.session_factory.begin() as db_session:
        context = db_session.get(ServerContextModel, "123")
        assert context is not None
        context.current_session = None
    renderer = JournalRenderer(campaigns, sessions, quests, 123)

    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    import asyncio

    asyncio.run(renderer._progress_modal(interaction, quest.id))
    interaction.response.send_message.assert_awaited_once()
    assert "No session is currently selected" in (
        interaction.response.send_message.await_args.args[0]
    )
    assert session.id == 1


def test_journal_command_sends_one_interactive_panel(tmp_path):
    renderer, sessions, _, _, _ = setup_journal(tmp_path)
    cog = CampaignCommands(renderer.campaigns)
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    import asyncio

    asyncio.run(cast(Any, cog.journal.callback)(cog, ctx))
    ctx.send.assert_awaited_once()
    assert ctx.send.await_args.kwargs["embed"].title == "JOURNAL"
    assert ctx.send.await_args.kwargs["view"].children
    assert sessions.current(123).title == "Opening"


def test_journal_command_reports_missing_campaign(tmp_path):
    database = tmp_path / "journal.sqlite3"
    cog = CampaignCommands(CampaignStore(database))
    ctx = MagicMock()
    ctx.guild = SimpleNamespace(id=123)
    ctx.send = AsyncMock()

    import asyncio

    asyncio.run(cast(Any, cog.journal.callback)(cog, ctx))
    ctx.send.assert_awaited_once()
    assert "No campaign is currently selected" in ctx.send.await_args.args[0]
