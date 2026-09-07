"""Discord interactive journal panel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime as dt
from math import ceil
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast

import discord

from journalbot.campaigns import CampaignError, CampaignStore
from journalbot.quests import Quest, QuestError, QuestStore
from journalbot.sessions import SessionError, SessionStore

PAGE_SIZE = 5
SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━"


@dataclass(frozen=True)
class _JournalLayoutBuilder:
    """Direct Components V2 layout helpers for one journal screen."""

    content: str
    view: discord.ui.LayoutView
    fields: tuple[tuple[str, str, bool], ...] = ()
    kind: str = "generic"

    def _add_dashboard_layout(
        self, layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
    ) -> None:
        """Place the complete dashboard inside one Components V2 container."""
        filter_buttons = [
            button
            for button in buttons
            if button.custom_id
            in {
                "j:q:list:all:0",
                "j:q:list:active:0",
                "j:q:list:completed:0",
                "j:q:list:failed:0",
            }
        ]
        recent_buttons = [
            button
            for button in buttons
            if button.custom_id and button.custom_id.startswith("j:q:view:")
        ]
        trailing_buttons = [
            button
            for button in buttons
            if button not in filter_buttons and button not in recent_buttons
        ]
        campaign_index = next(
            index for index, field in enumerate(self.fields) if field[0] != SEPARATOR
        )
        campaign_name, campaign_value, _ = self.fields[campaign_index]
        quests_index = next(
            index
            for index, field in enumerate(
                self.fields[campaign_index + 1 :], campaign_index + 1
            )
            if field[0] == "Quests"
        )
        stats: list[tuple[str, str]] = []
        stats_end = quests_index + 1
        while stats_end < len(self.fields) and self.fields[stats_end][2]:
            name, value, _ = self.fields[stats_end]
            stats.append((name, value))
            stats_end += 1

        children: list[discord.ui.Item[Any]] = [
            discord.ui.TextDisplay(self.content),
            discord.ui.TextDisplay(f"### **{campaign_name}**\n{campaign_value}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay("### **Quests**"),
            discord.ui.TextDisplay(
                "  \u2502  ".join(f"**{name}** {value}" for name, value in stats)
            ),
        ]
        if filter_buttons:
            children.append(discord.ui.ActionRow(*filter_buttons))
        children.append(discord.ui.Separator())

        recent_started = False
        for name, value, _ in self.fields[stats_end:]:
            if name == "Recent activity":
                recent_started = True
                children.append(discord.ui.TextDisplay(f"### **{name}**"))
            elif recent_started and recent_buttons:
                children.append(
                    discord.ui.Section(
                        discord.ui.TextDisplay(f"**{name}**\n{value}"),
                        accessory=recent_buttons.pop(0),
                    )
                )
                children.append(discord.ui.Separator())

        if not recent_started:
            children.append(discord.ui.TextDisplay("**Recent activity**"))
        for index in range(0, len(trailing_buttons), 5):
            children.append(discord.ui.ActionRow(*trailing_buttons[index : index + 5]))

        # Discord Components V2 prohibits nested containers; this single outer
        # container provides the dashboard background and retains all content.
        layout.add_item(discord.ui.Container(*children, accent_color=0x46D789))

    def _add_quest_list_layout(
        self, layout: discord.ui.Container, buttons: list[discord.ui.Button]
    ) -> None:
        filters = [
            button
            for button in buttons
            if button.custom_id and button.custom_id.startswith("j:q:list:")
        ]
        quest_buttons = [
            button
            for button in buttons
            if button.custom_id and button.custom_id.startswith("j:q:view:")
        ]
        trailing = [
            button for button in buttons if button not in filters + quest_buttons
        ]

        layout.add_item(discord.ui.Separator())
        _add_button_row(layout, filters)
        layout.add_item(discord.ui.Separator())
        quest_index = 0
        for name, value, _ in self.fields:
            if name.startswith("Page "):
                layout.add_item(discord.ui.TextDisplay(f"*{name}*"))
                continue
            if quest_index < len(quest_buttons):
                layout.add_item(
                    discord.ui.Section(
                        discord.ui.TextDisplay(f"**{name}**\n{value}"),
                        accessory=quest_buttons[quest_index],
                    )
                )
                quest_index += 1
                layout.add_item(discord.ui.Separator())
            else:
                layout.add_item(discord.ui.TextDisplay(f"**{name}**\n{value}"))
        _add_button_rows(layout, trailing)

    def _add_session_list_layout(
        self, layout: discord.ui.Container, buttons: list[discord.ui.Button]
    ) -> None:
        session_buttons = [
            button
            for button in buttons
            if button.custom_id and button.custom_id.startswith("j:s:view:")
        ]
        trailing = [button for button in buttons if button not in session_buttons]
        layout.add_item(discord.ui.Separator())
        for index, (name, value, _) in enumerate(self.fields):
            if name.startswith("Page "):
                layout.add_item(discord.ui.TextDisplay(f"*{name}*"))
                continue
            if index < len(session_buttons):
                layout.add_item(
                    discord.ui.Section(
                        discord.ui.TextDisplay(f"**{name}**\n{value}"),
                        accessory=session_buttons[index],
                    )
                )
                layout.add_item(discord.ui.Separator())
            else:
                layout.add_item(discord.ui.TextDisplay(f"**{name}**\n{value}"))
        _add_button_rows(layout, trailing)

    def _add_quest_details_layout(
        self, layout: discord.ui.Container, buttons: list[discord.ui.Button]
    ) -> None:
        layout.add_item(discord.ui.Separator())
        self._add_fields(layout)
        _add_button_rows(layout, buttons)

    def _add_session_details_layout(
        self, layout: discord.ui.Container, buttons: list[discord.ui.Button]
    ) -> None:
        layout.add_item(discord.ui.Separator())
        self._add_fields(layout)
        _add_button_rows(layout, buttons)

    def _add_fields(self, layout: discord.ui.Container) -> None:
        for name, value, _ in self.fields:
            if name == SEPARATOR:
                layout.add_item(discord.ui.Separator())
                continue
            layout.add_item(discord.ui.TextDisplay(f"**{name}**\n{value}"))


@dataclass(frozen=True)
class JournalRender:
    """A completed Components V2 journal message."""

    view: discord.ui.LayoutView


def _render_layout(
    content: str,
    fields: tuple[tuple[str, str, bool], ...],
    kind: str,
    button_specs: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    callback: Callable[[discord.Interaction, str], Awaitable[None]],
) -> JournalRender:
    """Build one journal screen directly with Components V2 objects."""
    layout = discord.ui.LayoutView(timeout=900)
    buttons = _buttons(button_specs, callback)
    builder = _JournalLayoutBuilder(content, layout, fields, kind)

    if kind == "dashboard":
        builder._add_dashboard_layout(layout, buttons)
    else:
        panel: discord.ui.Container[Any] = discord.ui.Container(accent_color=0x46D789)
        panel.add_item(discord.ui.TextDisplay(content))
        if kind == "quest_list":
            builder._add_quest_list_layout(panel, buttons)
        elif kind == "session_list":
            builder._add_session_list_layout(panel, buttons)
        elif kind == "quest_details":
            builder._add_quest_details_layout(panel, buttons)
        elif kind == "session_details":
            builder._add_session_details_layout(panel, buttons)
        else:
            panel.add_item(discord.ui.Separator())
            builder._add_fields(panel)
            _add_button_rows(panel, buttons)
        layout.add_item(panel)
    return JournalRender(layout)


class JournalRenderer:
    """Loads journal data and renders each interactive view."""

    def __init__(
        self,
        campaigns: CampaignStore,
        sessions: SessionStore,
        quests: QuestStore,
        guild_id: int,
    ) -> None:
        self.campaigns = campaigns
        self.sessions = sessions
        self.quests = quests
        self.guild_id = guild_id

    def dashboard(self) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        try:
            current_session = self.sessions.current(self.guild_id)
            session_text = f"#{current_session.number} — {current_session.title}"
        except SessionError:
            current_session = None
            session_text = "(none selected)"
        quests = list(self.quests.list(self.guild_id))
        counts = {
            "ACTIVE": sum(item.status == "ACTIVE" for item in quests),
            "COMPLETED": sum(item.status == "COMPLETED" for item in quests),
            "FAILED": sum(item.status == "FAILED" for item in quests),
        }
        recent_quests = list(reversed(quests))[:4]
        lines = [
            "## JOURNAL",
            "",
            "Here's your campaign journal. Select a category to see more details.",
        ]
        fields: list[tuple[str, str, bool]] = [
            (SEPARATOR, "\u200b", False),
            (
                f"🛡️  {campaign.title}",
                (campaign.description or "Campaign") + "\n\u200b",
                False,
            ),
            (SEPARATOR, "\u200b", False),
            ("Quests", "\u200b", False),
            ("⚔️  " + str(counts["ACTIVE"]), "Active ", True),
            ("✅  " + str(counts["COMPLETED"]), "Completed", True),
            ("❌  " + str(counts["FAILED"]), "Failed", True),
            ("🗓️  " + session_text, "", True),
        ]
        if recent_quests:
            fields.append(("Recent activity", "\u200b", False))
            for quest in recent_quests:
                progress = self.quests.list_progress(self.guild_id, str(quest.id))
                last_progress = (
                    f"Last progress: {progress[-1].description}"
                    if progress
                    else "No progress recorded yet."
                )
                fields.append(
                    (
                        f"{quest.title}",
                        f"{_status_label(quest.status)}  ·  {last_progress}",
                        False,
                    )
                )
        else:
            fields.append(("Recent activity", "No quests recorded yet.", False))

        buttons: list[tuple[str, str]] = [
            ("Active", "j:q:list:active:0"),
            ("Completed", "j:q:list:completed:0"),
            ("Failed", "j:q:list:failed:0"),
        ]
        buttons.extend(
            (quest.title[:80], f"j:q:view:{quest.id}") for quest in recent_quests
        )
        buttons.extend(
            [
                ("View all quests", "j:q:all:0"),
                ("Sessions", "j:s:list:0"),
                ("Create Quest", "j:q:create"),
            ]
        )
        return _render_layout(
            "\n".join(lines),
            tuple(fields),
            "dashboard",
            buttons,
            self._route,
        )

    def quest_list(self, filter_name: str, page: int) -> JournalRender:
        if filter_name not in {"all", "active", "completed", "failed"}:
            filter_name = "all"
        items = list(self.quests.list(self.guild_id, filter_name))
        return self._paged_quest_list(items, filter_name, page)

    def _paged_quest_list(
        self, items: Sequence[Quest], filter_name: str, page: int
    ) -> JournalRender:
        pages = max(1, ceil(len(items) / PAGE_SIZE))
        page = min(max(page, 0), pages - 1)
        selected = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = [
            "## "
            + ("ALL" if filter_name == "all" else filter_name.upper())
            + " QUESTS",
            "",
            f"Showing {len(items)} {filter_name} quests in this campaign.",
        ]
        fields = [
            (
                f"### {item.title} — {_status_label(item.status)}",
                (
                    f"{item.description or 'No description.'}\n"
                    f"**Giver:** {item.quest_giver or 'Unknown'}  ·  "
                    f"**Session:** {item.started_session_id}"
                ),
                False,
            )
            for item in selected
        ]
        if not selected:
            fields.append(("No quests found.", "\u200b", False))
        buttons: list[tuple[str, str]] = [
            ("All quests", f"j:q:list:all:{page}"),
            ("Active", f"j:q:list:active:{page}"),
            ("Completed", f"j:q:list:completed:{page}"),
            ("Failed", f"j:q:list:failed:{page}"),
        ]
        buttons.extend((item.title[:80], f"j:q:view:{item.id}") for item in selected)

        if page > 0:
            buttons.append(("‹  Prev", f"j:q:page:{filter_name}:{page - 1}"))

        if page < pages - 1:
            buttons.append(("Next  ›", f"j:q:page:{filter_name}:{page + 1}"))

        buttons.extend(
            [
                ("Back", "j:home"),
            ]
        )

        fields.append((f"Page {page + 1} / {pages}", "\u200b", False))
        return _render_layout(
            "\n".join(lines), tuple(fields), "quest_list", buttons, self._route
        )

    def quest_details(
        self, quest_id: int, filter_name: str, page: int
    ) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        quest = self.quests.find(str(quest_id), campaign.id)
        session = self.sessions.find(str(quest.started_session_id), campaign.id)
        session_title_to_display = session.title or quest.started_session_id
        progress = self.quests.list_progress(self.guild_id, str(quest_id))
        lines = [
            f"## {quest.title} {_quest_emoji(quest.status)}",
            f"{quest.description or 'No description.'}",
        ]
        detail_fields: list[tuple[str, str, bool]] = [
            ("Status:", _status_label(quest.status), True),
            ("👤 Quest giver:", quest.quest_giver or "Nieznany", True),
            ("📍 Received at", quest.received_at_location or "Nieznany", True),
            (
                "🗓️ Started in",
                f"{session_title_to_display} (ID:{quest.started_session_id})",
                True,
            ),
            (SEPARATOR, "\u200b", False),
        ]
        if progress:
            progress_section_start = f"📖 Progress ({len(progress)} entries):"
            progress_section_entries = []

            for entry in progress:
                entry_session_title = self.sessions.find(
                    str(entry.session_id), campaign.id
                ).title
                progress_section_entries.append(
                    f"🗡️ **Session {entry.session_id}: {entry_session_title} ** \n"
                    f"{entry.description}"
                )

            progress_section_entry = "\n".join(progress_section_entries)

            detail_fields.append(
                (
                    progress_section_start,
                    progress_section_entry,
                    False,
                )
            )
        else:
            detail_fields.append(("📖 Progress (0 entries)", "(none)", False))
        buttons: list[tuple[str, str]] = [("Back", f"j:q:back:{filter_name}:{page}")]
        if quest.status == "ACTIVE":
            buttons.extend(
                [
                    ("Add progress", f"j:q:progress:{quest.id}"),
                    ("Complete", f"j:q:complete:{quest.id}:{filter_name}:{page}"),
                    ("Fail", f"j:q:fail:{quest.id}:{filter_name}:{page}"),
                ]
            )
        return _render_layout(
            "\n".join(lines),
            tuple(detail_fields),
            "quest_details",
            buttons,
            self._route,
        )

    def session_list(self, page: int) -> JournalRender:
        items = list(reversed(self.sessions.list_current_campaign(self.guild_id)))
        pages = max(1, ceil(len(items) / PAGE_SIZE))
        page = min(max(page, 0), pages - 1)
        selected = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = ["## SESSIONS"]

        session_fields = [
            (
                f"🗓️  Session #{item.number} — {item.title}",
                f"Played at: {dt.fromisoformat(item.played_at).strftime('%Y-%m-%d')}\n"
                f"**Status:** {_status_label(item.status)}",
                False,
            )
            for item in selected
        ]
        if not selected:
            session_fields.append(("No sessions found.", "\u200b", False))
        buttons = [
            (f"Session #{item.number} — {item.title}"[:80], f"j:s:view:{item.id}")
            for item in selected
        ]

        if page > 0:
            buttons.append(("‹  Prev", f"j:s:page:{page - 1}"))

        if page < pages - 1:
            buttons.append(("Next  ›", f"j:s:page:{page + 1}"))

        buttons.extend(
            [
                ("Back", "j:home"),
            ]
        )

        session_fields.append((f"Page {page + 1} / {pages}", "\u200b", False))
        return _render_layout(
            "\n".join(lines),
            tuple(session_fields),
            "session_list",
            buttons,
            self._route,
        )

    def session_details(self, session_id: int, page: int) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        session = self.sessions.find(str(session_id), campaign.id)
        events = self.sessions.list_journal_events_for_session(session.id)
        progress = self.quests.list_for_session(session.id)
        played_at = dt.fromisoformat(session.played_at).strftime("%Y-%m-%d")

        lines = [
            f"## SESSION #{session.number} - Played at {played_at}",
            f"**{session.title}**",
        ]
        detail_fields: list[tuple[str, str, bool]] = []
        if events:
            detail_fields.append(
                (
                    f"### 📜 Journal Events ({len(events)})",
                    "\n".join(f"📌 {event.description}" for event in events),
                    False,
                )
            )
        else:
            detail_fields.append(("Events (0)", "(none)", False))
        detail_fields.append((SEPARATOR, "\u200b", False))
        if progress:
            detail_fields.append(
                (
                    f"### 📖 Quest Progress ({len(progress)})",
                    "\n".join(
                        f"🗡️ **{entry.quest_title}** — {entry.description}"
                        for entry in progress
                    ),
                    False,
                )
            )
        else:
            detail_fields.append(("Progress (0)", "(none)", False))
        detail_fields.append((SEPARATOR, "\u200b", False))
        return _render_layout(
            "\n".join(lines),
            tuple(detail_fields),
            "session_details",
            (("Back", f"j:s:back:{page}"),),
            self._route,
        )

    async def _route(self, interaction: discord.Interaction, custom_id: str) -> None:
        try:
            parts = custom_id.split(":")
            action = parts[1:]
            if custom_id == "j:home":
                await _edit(interaction, self.dashboard())
            elif action[:2] == ["q", "list"]:
                await _edit(interaction, self.quest_list(action[2], int(action[3])))
            elif action[:2] == ["q", "page"]:
                await _edit(interaction, self.quest_list(action[2], int(action[3])))
            elif action[:2] == ["q", "all"]:
                await _edit(interaction, self.quest_list("all", int(action[2])))
            elif action[:2] == ["q", "view"]:
                await _edit(interaction, self.quest_details(int(action[2]), "all", 0))
            elif action[:2] == ["q", "back"]:
                await _edit(interaction, self.quest_list(action[2], int(action[3])))
            elif action[:2] == ["q", "progress"]:
                await self._progress_modal(interaction, int(action[2]))
            elif action[:2] == ["q", "create"]:
                await interaction.response.send_modal(CreateQuestModal(self))
            elif action[:2] in (["q", "complete"], ["q", "fail"]):
                await _edit(
                    interaction,
                    self._confirmation(
                        action[0], action[1], int(action[2]), action[3], int(action[4])
                    ),
                )
            elif action[:2] in (["q", "confirm-complete"], ["q", "confirm-fail"]):
                await self._confirm(interaction, action)
            elif action[:2] == ["q", "cancel"]:
                await _edit(
                    interaction,
                    self.quest_details(int(action[2]), action[3], int(action[4])),
                )
            elif action[:2] == ["s", "list"]:
                await _edit(interaction, self.session_list(int(action[2])))
            elif action[:2] == ["s", "page"]:
                await _edit(interaction, self.session_list(int(action[2])))
            elif action[:2] == ["s", "view"]:
                await _edit(interaction, self.session_details(int(action[2]), 0))
            elif action[:2] == ["s", "back"]:
                await _edit(interaction, self.session_list(int(action[2])))
            else:
                await _error(interaction, "This journal action is no longer valid.")
        except (CampaignError, QuestError, SessionError, ValueError) as error:
            await _error(interaction, str(error))

    def _confirmation(
        self, resource: str, action: str, quest_id: int, filter_name: str, page: int
    ) -> JournalRender:
        verb = "Complete" if action == "complete" else "Fail"
        content = (
            f"## {verb} Quest?\n\nConfirm changing this quest to **{verb.upper()}**."
        )
        buttons = [
            (
                "Confirm",
                f"j:q:confirm-{action}:{quest_id}:{filter_name}:{page}",
            ),
            ("Cancel", f"j:q:cancel:{quest_id}:{filter_name}:{page}"),
        ]
        return _render_layout(content, (), "confirmation", buttons, self._route)

    async def _confirm(
        self, interaction: discord.Interaction, action: list[str]
    ) -> None:
        quest_id, filter_name, page = int(action[2]), action[3], int(action[4])
        campaign = self.campaigns.current(self.guild_id)
        quest = self.quests.find(str(quest_id), campaign.id)
        if quest.status != "ACTIVE":
            await _edit(interaction, self.quest_details(quest_id, filter_name, page))
            return
        if action[1] == "confirm-complete":
            self.quests.complete(self.guild_id, str(quest_id))
        else:
            self.quests.fail(self.guild_id, str(quest_id))
        await _edit(interaction, self.quest_details(quest_id, filter_name, page))

    async def _progress_modal(
        self, interaction: discord.Interaction, quest_id: int
    ) -> None:
        if not _has_current_session(self.sessions, self.guild_id):
            await _error(
                interaction,
                "No session is currently selected. "
                "Select a current session before adding quest progress.",
            )
            return
        await interaction.response.send_modal(ProgressModal(self, quest_id))

    async def save_progress(
        self, interaction: discord.Interaction, quest_id: int, description: str
    ) -> None:
        self.quests.add_progress(self.guild_id, str(quest_id), description)
        await _edit(interaction, self.quest_details(quest_id, "all", 0))

    async def create_quest(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        quest_giver: str | None,
        received_at_location: str | None,
    ) -> None:
        """Create a quest from the dashboard modal and refresh the dashboard."""
        self.quests.create(
            self.guild_id,
            title,
            description,
            quest_giver,
            received_at_location,
        )
        await _edit(interaction, self.dashboard())


class ProgressModal(discord.ui.Modal, title="Add Quest Progress"):
    """Modal for creating one immutable quest progress entry."""

    description: discord.ui.TextInput = discord.ui.TextInput(
        label="What happened?",
        custom_id="description",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    def __init__(self, renderer: JournalRenderer, quest_id: int) -> None:
        super().__init__(custom_id=f"j:m:progress:{quest_id}")
        self.renderer = renderer
        self.quest_id = quest_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.renderer.save_progress(
                interaction, self.quest_id, str(self.description.value)
            )
        except (CampaignError, QuestError, SessionError, ValueError) as error:
            await _error(interaction, str(error))


class CreateQuestModal(discord.ui.Modal, title="Create Quest"):
    """Modal equivalent of the !create-quest command."""

    quest_title: discord.ui.TextInput = discord.ui.TextInput(
        label="Title",
        custom_id="title",
        required=True,
    )
    description: discord.ui.TextInput = discord.ui.TextInput(
        label="Description",
        custom_id="description",
        style=discord.TextStyle.paragraph,
        required=True,
    )
    quest_giver: discord.ui.TextInput = discord.ui.TextInput(
        label="Quest giver",
        custom_id="quest_giver",
        required=False,
    )
    received_at_location: discord.ui.TextInput = discord.ui.TextInput(
        label="Received at location",
        custom_id="received_at_location",
        required=False,
    )

    def __init__(self, renderer: JournalRenderer) -> None:
        super().__init__(custom_id="j:m:create-quest")
        self.renderer = renderer

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self.renderer.create_quest(
                interaction,
                str(self.quest_title.value),
                str(self.description.value),
                str(self.quest_giver.value) or None,
                str(self.received_at_location.value) or None,
            )
        except (CampaignError, QuestError, SessionError, ValueError) as error:
            await _error(interaction, str(error))


def _has_current_session(sessions: SessionStore, guild_id: int) -> bool:
    try:
        sessions.current(guild_id)
    except SessionError:
        return False
    return True


def _buttons(
    buttons: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    callback: Callable[[discord.Interaction, str], Awaitable[None]],
) -> list[discord.ui.Button]:
    components: list[discord.ui.Button] = []
    for label, custom_id in buttons:
        button: discord.ui.Button[Any] = discord.ui.Button(
            label=label,
            custom_id=custom_id,
            style=_button_style(custom_id),
            emoji=_button_emoji(custom_id, label),
        )

        async def clicked(
            interaction: discord.Interaction,
            button: discord.ui.Button[Any] = button,
        ) -> None:
            await callback(interaction, button.custom_id or "")

        cast(Any, button).callback = clicked
        components.append(button)
    return components


async def _edit(interaction: discord.Interaction, rendered: JournalRender) -> None:
    if interaction.response.is_done():
        await interaction.edit_original_response(view=rendered.view)
    else:
        await interaction.response.edit_message(view=rendered.view)


async def _error(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def _add_button_row(
    layout: discord.ui.LayoutView | discord.ui.Container[Any],
    buttons: list[discord.ui.Button],
) -> None:
    if buttons:
        layout.add_item(discord.ui.ActionRow(*buttons))


def _add_button_rows(
    layout: discord.ui.LayoutView | discord.ui.Container[Any],
    buttons: list[discord.ui.Button],
) -> None:
    for index in range(0, len(buttons), 5):
        _add_button_row(layout, buttons[index : index + 5])


def _button_style(custom_id: str) -> discord.ButtonStyle:
    """Map journal actions to the semantic colors used in the reference design."""
    if ":list:all:" in custom_id or custom_id in {"j:q:all:0", "j:s:list:0"}:
        return discord.ButtonStyle.primary
    if ":list:active:" in custom_id:
        return discord.ButtonStyle.secondary
    if ":progress:" in custom_id or custom_id == "j:q:create":
        return discord.ButtonStyle.primary
    if ":confirm-fail:" in custom_id:
        return discord.ButtonStyle.danger
    return discord.ButtonStyle.secondary


def _quest_emoji(status: str) -> str:
    return {
        "ACTIVE": "⚔️",
        "COMPLETED": "✅",
        "FAILED": "❌",
    }.get(status, "📜")


def _status_label(status: str) -> str:
    return {
        "ACTIVE": f"{_quest_emoji('ACTIVE')} Active",
        "COMPLETED": f"{_quest_emoji('COMPLETED')} Completed",
        "FAILED": f"{_quest_emoji('FAILED')} Completed",
    }.get(status, status.title())


def _button_emoji(custom_id: str, label: str) -> str | None:
    """Return a compact icon for a component without putting it in the label."""
    if custom_id == "j:home" or ":back:" in custom_id:
        return "◀️"
    if ":list:all:" in custom_id or custom_id == "j:q:all:0":
        return "📜"
    if ":list:active:" in custom_id:
        return "⚔️"
    if ":list:completed:" in custom_id:
        return "✅"
    if ":list:failed:" in custom_id:
        return "❌"
    if ":progress:" in custom_id or custom_id == "j:q:create":
        return "➕"
    if ":complete" in custom_id or ":confirm-complete:" in custom_id:
        return "✅"
    if ":fail" in custom_id or ":confirm-fail:" in custom_id:
        return "❌"
    if ":view:" in custom_id and custom_id.startswith("j:q:"):
        return "📜"
    if ":view:" in custom_id and custom_id.startswith("j:s:"):
        return "🗓️"
    if custom_id == "j:s:list:0":
        return "🗓️"
    return None
