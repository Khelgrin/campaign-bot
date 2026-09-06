"""Discord interactive journal panel."""

from __future__ import annotations

from dataclasses import dataclass
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
class JournalRender:
    """Complete message state for one journal view."""

    content: str
    view: discord.ui.View | discord.ui.LayoutView
    fields: tuple[tuple[str, str, bool], ...] = ()
    kind: str = "generic"

    def __post_init__(self) -> None:
        """Convert the classic button view into a Components V2 layout."""
        if isinstance(self.view, discord.ui.LayoutView):
            return
        legacy_view = self.view
        layout = discord.ui.LayoutView(timeout=legacy_view.timeout)
        layout.add_item(discord.ui.TextDisplay(self.content))
        buttons = [
            item
            for item in legacy_view.children
            if isinstance(item, discord.ui.Button)
        ]
        if self.kind == "dashboard":
            self._add_dashboard_layout(layout, buttons)
        elif self.kind == "quest_list":
            self._add_quest_list_layout(layout, buttons)
        elif self.kind == "session_list":
            self._add_session_list_layout(layout, buttons)
        elif self.kind == "quest_details":
            self._add_quest_details_layout(layout, buttons)
        elif self.kind == "session_details":
            self._add_session_details_layout(layout, buttons)
        else:
            layout.add_item(discord.ui.Separator())
            self._add_fields(layout)
            _add_button_rows(layout, buttons)
        object.__setattr__(self, "view", layout)

    def _add_dashboard_layout(
        self, layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
    ) -> None:
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

        summary_children: list[discord.ui.Item[Any]] = [
            discord.ui.TextDisplay(f"**{campaign_name}**\n{campaign_value}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay("**Quests**"),
            discord.ui.TextDisplay(
                "  │  ".join(f"**{name}** {value}" for name, value in stats)
            ),
        ]
        layout.add_item(
            discord.ui.Container(*summary_children, accent_color=0x34D399)
        )
        _add_button_row(layout, filter_buttons)
        layout.add_item(discord.ui.Separator())

        recent_started = False
        activity_children: list[discord.ui.Item[Any]] = []
        for name, value, _ in self.fields[stats_end:]:
            if name == "Recent activity":
                recent_started = True
                activity_children.append(discord.ui.TextDisplay(f"**{name}**\n{value}"))
            elif recent_started and recent_buttons:
                activity_children.append(
                    discord.ui.Section(
                        discord.ui.TextDisplay(f"**{name}**\n{value}"),
                        accessory=recent_buttons.pop(0),
                    )
                )
        if recent_started:
            layout.add_item(
                discord.ui.Container(*activity_children, accent_color=0x334155)
            )
        else:
            layout.add_item(discord.ui.Container(
                discord.ui.TextDisplay("**Recent activity**"),
                accent_color=0x334155,
            ))
        _add_button_rows(layout, trailing_buttons)

    def _add_quest_list_layout(
        self, layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
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
            else:
                layout.add_item(discord.ui.TextDisplay(f"**{name}**\n{value}"))
        _add_button_rows(layout, trailing)

    def _add_session_list_layout(
        self, layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
    ) -> None:
        session_buttons = [
            button
            for button in buttons
            if button.custom_id and button.custom_id.startswith("j:s:view:")
        ]
        trailing = [button for button in buttons if button not in session_buttons]
        layout.add_item(discord.ui.Separator())
        for index, (name, value, _) in enumerate(self.fields):
            if index < len(session_buttons):
                layout.add_item(
                    discord.ui.Section(
                        discord.ui.TextDisplay(f"**{name}**\n{value}"),
                        accessory=session_buttons[index],
                    )
                )
            else:
                layout.add_item(discord.ui.TextDisplay(f"**{name}**\n{value}"))
        _add_button_rows(layout, trailing)

    def _add_quest_details_layout(
        self, layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
    ) -> None:
        layout.add_item(discord.ui.Separator())
        self._add_fields(layout)
        _add_button_rows(layout, buttons)

    def _add_session_details_layout(
        self, layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
    ) -> None:
        layout.add_item(discord.ui.Separator())
        self._add_fields(layout)
        _add_button_rows(layout, buttons)

    def _add_fields(self, layout: discord.ui.LayoutView) -> None:
        inline_fields: list[tuple[str, str]] = []
        for name, value, inline in self.fields:
            if name == SEPARATOR:
                _flush_inline_fields(layout, inline_fields)
                layout.add_item(discord.ui.Separator())
                continue
            if inline:
                inline_fields.append((name, value))
                continue
            _flush_inline_fields(layout, inline_fields)
            layout.add_item(discord.ui.TextDisplay(f"**{name}**\n{value}"))
        _flush_inline_fields(layout, inline_fields)

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
            ("📜  " + str(counts["ACTIVE"]), "Active", True),
            ("✅  " + str(counts["COMPLETED"]), "Completed", True),
            ("❌  " + str(counts["FAILED"]), "Failed", True),
            ("🗓️  " + session_text, "Current Session", True),
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
                        f"{_quest_emoji(quest.status)}  {quest.title}",
                        f"{_status_label(quest.status)}  ·  {last_progress}",
                        False,
                    )
                )
        else:
            fields.append(("Recent activity", "No quests recorded yet.", False))

        buttons: list[tuple[str, str]] = [
            ("All Quests", "j:q:list:all:0"),
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
            ]
        )
        return JournalRender(
            "\n".join(lines),
            _view(buttons, self._route),
            tuple(fields),
            "dashboard",
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
                f"{_quest_emoji(item.status)}  {item.title} — "
                f"{_status_label(item.status)}",
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
        buttons.extend(
            (item.title[:80], f"j:q:view:{item.id}")
            for item in selected
        )
        buttons.extend(
            [
                ("Back", "j:home"),
            ]
        )
        view = _view(buttons, self._route)
        fields.append((f"Page {page + 1} / {pages}", "\u200b", False))
        return JournalRender(
            "\n".join(lines), view, tuple(fields), "quest_list"
        )

    def quest_details(
        self, quest_id: int, filter_name: str, page: int
    ) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        quest = self.quests.find(str(quest_id), campaign.id)
        progress = self.quests.list_progress(self.guild_id, str(quest_id))
        lines = [f"## {quest.title}"]
        detail_fields: list[tuple[str, str, bool]] = [
            ("Status", _status_label(quest.status), False),
            ("👤 Quest giver", quest.quest_giver or "(none)", True),
            ("📍 Received at", quest.received_at_location or "(none)", True),
            ("🗓️ Started in", f"Session {quest.started_session_id}", True),
            ("Description", quest.description or "(none)", False),
        ]
        if progress:
            detail_fields.append(
                (
                    f"📖 Progress ({len(progress)} entries)",
                    "\n".join(
                        f"🟢 **Session {entry.session_id}**  {entry.description}"
                        for entry in progress
                    ),
                    False,
                )
            )
        else:
            detail_fields.append(("📖 Progress (0 entries)", "(none)", False))
        buttons: list[tuple[str, str]] = [
            ("Back", f"j:q:back:{filter_name}:{page}")
        ]
        if quest.status == "ACTIVE":
            buttons.extend(
                [
                    ("Add progress", f"j:q:progress:{quest.id}"),
                    ("Complete", f"j:q:complete:{quest.id}:{filter_name}:{page}"),
                    ("Fail", f"j:q:fail:{quest.id}:{filter_name}:{page}"),
                ]
            )
        return JournalRender(
            "\n".join(lines),
            _view(buttons, self._route),
            tuple(detail_fields),
            "quest_details",
        )

    def session_list(self, page: int) -> JournalRender:
        items = list(reversed(self.sessions.list_current_campaign(self.guild_id)))
        pages = max(1, ceil(len(items) / PAGE_SIZE))
        page = min(max(page, 0), pages - 1)
        selected = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = ["## SESSIONS", "", "Sessions in this campaign."]
        session_fields = [
            (
                f"🗓️  Session #{item.number} — {item.title}",
                f"{item.played_at}\n**Status:** {_status_label(item.status)}",
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
        buttons.extend(
            [
                ("Back", "j:home"),
            ]
        )
        view = _view(buttons, self._route)
        session_fields.append((f"Page {page + 1} / {pages}", "\u200b", False))
        return JournalRender(
            "\n".join(lines), view, tuple(session_fields), "session_list"
        )

    def session_details(self, session_id: int, page: int) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        session = self.sessions.find(str(session_id), campaign.id)
        events = self.sessions.list_journal_events_for_session(session.id)
        progress = self.quests.list_for_session(session.id)
        lines = [f"## SESSION #{session.number}", f"**{session.title}**"]
        detail_fields: list[tuple[str, str, bool]] = [
            ("🗓️ Date", session.played_at, False),
            ("📜 Journal Events", "\u200b", False),
        ]
        if events:
            detail_fields.append(
                (
                    f"Events ({len(events)})",
                    "\n".join(f"📄 {event.description}" for event in events),
                    False,
                )
            )
        else:
            detail_fields.append(("Events (0)", "(none)", False))
        detail_fields.append(("📖 Quest Progress", "\u200b", False))
        if progress:
            detail_fields.append(
                (
                    f"Progress ({len(progress)})",
                    "\n".join(
                        f"**{entry.quest_title}** — {entry.description}"
                        for entry in progress
                    ),
                    False,
                )
            )
        else:
            detail_fields.append(("Progress (0)", "(none)", False))
        return JournalRender(
            "\n".join(lines),
            _view((("Back", f"j:s:back:{page}"),), self._route),
            tuple(detail_fields),
            "session_details",
        )

    async def _route(self, interaction: discord.Interaction, custom_id: str) -> None:
        try:
            parts = custom_id.split(":")
            action = parts[1:]
            if custom_id == "j:home":
                await _edit(interaction, self.dashboard())
            elif action[:2] == ["q", "list"]:
                await _edit(interaction, self.quest_list(action[2], int(action[3])))
            elif action[:2] == ["q", "all"]:
                await _edit(interaction, self.quest_list("all", int(action[2])))
            elif action[:2] == ["q", "view"]:
                await _edit(interaction, self.quest_details(int(action[2]), "all", 0))
            elif action[:2] == ["q", "back"]:
                await _edit(interaction, self.quest_list(action[2], int(action[3])))
            elif action[:2] == ["q", "progress"]:
                await self._progress_modal(interaction, int(action[2]))
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
            f"## {verb} Quest?\n\n"
            f"Confirm changing this quest to **{verb.upper()}**."
        )
        buttons = [
            (
                "Confirm",
                f"j:q:confirm-{action}:{quest_id}:{filter_name}:{page}",
            ),
            ("Cancel", f"j:q:cancel:{quest_id}:{filter_name}:{page}"),
        ]
        return JournalRender(content, _view(buttons, self._route))

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


def _has_current_session(sessions: SessionStore, guild_id: int) -> bool:
    try:
        sessions.current(guild_id)
    except SessionError:
        return False
    return True


def _view(
    buttons: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    callback: Callable[[discord.Interaction, str], Awaitable[None]],
) -> discord.ui.View:
    view = discord.ui.View(timeout=900)
    for label, custom_id in buttons:
        button: discord.ui.Button[discord.ui.View] = discord.ui.Button(
            label=label,
            custom_id=custom_id,
            style=_button_style(custom_id),
            emoji=_button_emoji(custom_id, label),
        )

        async def clicked(
            interaction: discord.Interaction,
            button: discord.ui.Button[discord.ui.View] = button,
        ) -> None:
            await callback(interaction, button.custom_id or "")

        cast(Any, button).callback = clicked
        view.add_item(button)
    return view


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


def _flush_inline_fields(
    layout: discord.ui.LayoutView, fields: list[tuple[str, str]]
) -> None:
    if not fields:
        return
    layout.add_item(
        discord.ui.TextDisplay(
            "  |  ".join(f"**{name}**\n{value}" for name, value in fields)
        )
    )
    fields.clear()


def _add_button_row(
    layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
) -> None:
    if buttons:
        layout.add_item(discord.ui.ActionRow(*buttons))


def _add_button_rows(
    layout: discord.ui.LayoutView, buttons: list[discord.ui.Button]
) -> None:
    for index in range(0, len(buttons), 5):
        _add_button_row(layout, buttons[index : index + 5])


def _button_style(custom_id: str) -> discord.ButtonStyle:
    """Map journal actions to the semantic colors used in the reference design."""
    if ":list:all:" in custom_id or custom_id in {"j:q:all:0", "j:s:list:0"}:
        return discord.ButtonStyle.primary
    if ":list:active:" in custom_id:
        return discord.ButtonStyle.success
    if ":progress:" in custom_id:
        return discord.ButtonStyle.primary
    if ":fail" in custom_id or ":confirm-fail:" in custom_id:
        return discord.ButtonStyle.danger
    return discord.ButtonStyle.secondary


def _quest_emoji(status: str) -> str:
    return {
        "ACTIVE": "📜",
        "COMPLETED": "⭐",
        "FAILED": "📕",
    }.get(status, "📜")


def _status_label(status: str) -> str:
    return {
        "ACTIVE": "🟢 Active",
        "COMPLETED": "✅ Completed",
        "FAILED": "❌ Failed",
    }.get(status, status.title())


def _button_emoji(custom_id: str, label: str) -> str | None:
    """Return a compact icon for a component without putting it in the label."""
    if custom_id == "j:home" or ":back:" in custom_id:
        return "◀️"
    if ":list:all:" in custom_id or custom_id == "j:q:all:0":
        return "📜"
    if ":list:active:" in custom_id:
        return "✅"
    if ":list:completed:" in custom_id:
        return "✅"
    if ":list:failed:" in custom_id:
        return "❌"
    if ":progress:" in custom_id:
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
