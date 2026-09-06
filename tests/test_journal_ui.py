"""Tests for the interactive journal renderer and component routing."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord

from journalbot.bot import CampaignCommands
from journalbot.campaigns import CampaignStore
from journalbot.database import ServerContextModel
from journalbot.journal_ui import JournalRender, JournalRenderer, ProgressModal
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


def view_buttons(
    view: discord.ui.View | discord.ui.LayoutView,
) -> list[discord.ui.Button]:
    return [
        item
        for row in view.children
        if isinstance(row, discord.ui.ActionRow)
        for item in row.children
        if isinstance(item, discord.ui.Button)
    ]


def view_text(view: discord.ui.LayoutView) -> str:
    chunks: list[str] = []
    for item in view.children:
        if isinstance(item, discord.ui.TextDisplay):
            chunks.append(item.content)
        elif isinstance(item, discord.ui.Container):
            chunks.extend(
                child.content
                for child in item.children
                if isinstance(child, discord.ui.TextDisplay)
            )
    return "\n".join(chunks)


def test_renderer_builds_dashboard_and_all_navigation_views(tmp_path):
    renderer, _, _, session, quest = setup_journal(tmp_path)

    dashboard = renderer.dashboard()
    assert "Kingmaker" in view_text(dashboard.view)
    assert "Opening" in view_text(dashboard.view)
    dashboard_ids = [item.custom_id for item in view_buttons(dashboard.view)]
    assert "j:q:list:all:0" in dashboard_ids
    assert "j:q:all:0" in dashboard_ids
    assert "j:s:list:0" in dashboard_ids

    quest_list = renderer.quest_list("all", 0)
    assert any(
        isinstance(item, discord.ui.TextDisplay)
        and "Find the Merchant" in item.content
        for item in quest_list.view.children
    )
    assert "j:q:view:" + str(quest.id) in {
        item.custom_id for item in view_buttons(quest_list.view)
    }
    assert any(
        isinstance(item, discord.ui.TextDisplay) and "Opening" in item.content
        for item in renderer.session_list(0).view.children
    )
    assert "The party found a hidden passage." in "\n".join(
        item.content
        for item in renderer.session_details(session.id, 0).view.children
        if isinstance(item, discord.ui.TextDisplay)
    )
    assert "Tracks lead toward the mine." in "\n".join(
        item.content
        for item in renderer.session_details(session.id, 0).view.children
        if isinstance(item, discord.ui.TextDisplay)
    )


def test_renderer_quest_details_and_confirmation_actions(tmp_path):
    renderer, _, quests, _, quest = setup_journal(tmp_path)
    details = renderer.quest_details(quest.id, "active", 0)
    custom_ids = [item.custom_id for item in view_buttons(details.view)]
    assert f"j:q:progress:{quest.id}" in custom_ids
    assert f"j:q:complete:{quest.id}:active:0" in custom_ids
    assert f"j:q:fail:{quest.id}:active:0" in custom_ids

    confirmation = renderer._confirmation("q", "complete", quest.id, "active", 0)
    assert f"j:q:confirm-complete:{quest.id}:active:0" in [
        item.custom_id for item in view_buttons(confirmation.view)
    ]
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.edit_message = AsyncMock()
    confirm_button = next(
        item
        for item in view_buttons(confirmation.view)
        if item.custom_id == f"j:q:confirm-complete:{quest.id}:active:0"
    )
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
    button = view_buttons(renderer.quest_list("all", 0).view)[-1]
    asyncio.run(button.callback(interaction))
    interaction.response.edit_message.assert_awaited_once()

    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_modal = AsyncMock()
    progress_button = next(
        item
        for item in view_buttons(renderer.quest_details(quest.id, "all", 0).view)
        if item.custom_id == f"j:q:progress:{quest.id}"
    )
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


def test_components_v2_rendering_and_empty_dashboard(tmp_path):
    import asyncio

    layout = discord.ui.LayoutView()
    rendered = JournalRender("## ACTIVE\n**Status:** ACTIVE", layout)
    assert rendered.view is layout

    database = tmp_path / "empty.sqlite3"
    campaigns = CampaignStore(database)
    campaigns.create(123, "Empty Campaign", None)
    renderer = JournalRenderer(
        campaigns, SessionStore(database), QuestStore(database), 123
    )
    dashboard = renderer.dashboard()
    assert "No quests recorded yet." in "\n".join(
        item.content
        for item in dashboard.view.children
        if isinstance(item, discord.ui.TextDisplay)
    )

    interaction = MagicMock()
    interaction.response.is_done.return_value = True
    interaction.edit_original_response = AsyncMock()
    view_all = next(
        item for item in view_buttons(dashboard.view) if item.custom_id == "j:q:all:0"
    )
    asyncio.run(view_all.callback(interaction))
    interaction.edit_original_response.assert_awaited_once()
