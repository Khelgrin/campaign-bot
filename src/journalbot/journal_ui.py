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


@dataclass(frozen=True)
class JournalRender:
    """Complete message state for one journal view."""

    content: str
    view: discord.ui.View

    @property
    def embed(self) -> discord.Embed:
        """Render the textual view as the journal's styled Discord card."""
        lines = self.content.splitlines()
        title = lines[0].removeprefix("## ").strip() if lines else "JOURNAL"
        description = "\n".join(lines[1:]).strip()
        embed = discord.Embed(
            title=title,
            description=description or None,
            color=discord.Color.blurple(),
        )
        return embed


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
            recent = self.sessions.list_journal_events(self.guild_id)[-3:]
        except SessionError:
            current_session = None
            session_text = "(none selected)"
            recent = []
        quests = list(self.quests.list(self.guild_id))
        counts = {
            "ACTIVE": sum(item.status == "ACTIVE" for item in quests),
            "COMPLETED": sum(item.status == "COMPLETED" for item in quests),
            "FAILED": sum(item.status == "FAILED" for item in quests),
        }
        lines = [
            "## JOURNAL",
            "",
            f"**Campaign:** {campaign.title}",
            f"**Session:** {session_text}",
            "",
            "**Quests**",
            f"Active: {counts['ACTIVE']}  •  Completed: {counts['COMPLETED']}  "
            f"•  Failed: {counts['FAILED']}",
        ]
        if recent:
            lines.extend(["", "**Recent Activity**"])
            lines.extend(f"• {event.description}" for event in recent)
        return JournalRender(
            "\n".join(lines),
            _view(
                (
                    ("📖  Quests", "j:q:list:all:0"),
                    ("📅  Sessions", "j:s:list:0"),
                ),
                self._route,
            ),
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
        lines = ["## QUESTS", "", "Filter: " + filter_name.upper(), ""]
        if selected:
            lines.extend(
                f"• {item.title} — {item.status}"
                for item in selected
            )
        else:
            lines.append("No quests found.")
        buttons: list[tuple[str, str]] = [
            ("📋  All quests", f"j:q:list:all:{page}"),
            ("🟢  Active", f"j:q:list:active:{page}"),
            ("✅  Completed", f"j:q:list:completed:{page}"),
            ("❌  Failed", f"j:q:list:failed:{page}"),
        ]
        buttons.extend(
            (f"📜  {item.title}"[:80], f"j:q:view:{item.id}")
            for item in selected
        )
        buttons.extend(
            [
                ("‹  Prev", f"j:q:list:{filter_name}:{page - 1}"),
                ("Next  ›", f"j:q:list:{filter_name}:{page + 1}"),
                ("←  Back", "j:home"),
            ]
        )
        view = _view(buttons, self._route)
        _set_enabled(view, f"j:q:list:{filter_name}:{page - 1}", page > 0)
        _set_enabled(view, f"j:q:list:{filter_name}:{page + 1}", page < pages - 1)
        lines.extend(["", f"Page {page + 1}/{pages}"])
        return JournalRender("\n".join(lines), view)

    def quest_details(
        self, quest_id: int, filter_name: str, page: int
    ) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        quest = self.quests.find(str(quest_id), campaign.id)
        progress = self.quests.list_progress(self.guild_id, str(quest_id))
        lines = [
            f"## {quest.title}",
            "",
            f"**Status:** {quest.status}",
            f"**Quest giver:** {quest.quest_giver or '(none)'}",
            f"**Received at:** {quest.received_at_location or '(none)'}",
            f"**Started in:** Session ID {quest.started_session_id}",
            "",
            "**Description**",
            quest.description or "(none)",
            "",
            "**Progress**",
        ]
        if progress:
            lines.extend(f"• {entry.description}" for entry in progress)
        else:
            lines.append("(none)")
        buttons: list[tuple[str, str]] = []
        if quest.status == "ACTIVE":
            buttons.extend(
                [
                    ("＋  Add progress", f"j:q:progress:{quest.id}"),
                    ("✓  Complete", f"j:q:complete:{quest.id}:{filter_name}:{page}"),
                    ("✕  Fail", f"j:q:fail:{quest.id}:{filter_name}:{page}"),
                ]
            )
        buttons.append(("←  Back", f"j:q:back:{filter_name}:{page}"))
        return JournalRender("\n".join(lines), _view(buttons, self._route))

    def session_list(self, page: int) -> JournalRender:
        items = list(reversed(self.sessions.list_current_campaign(self.guild_id)))
        pages = max(1, ceil(len(items) / PAGE_SIZE))
        page = min(max(page, 0), pages - 1)
        selected = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        lines = ["## SESSIONS", ""]
        if selected:
            lines.extend(
                f"• Session #{item.number} — {item.title}" for item in selected
            )
        else:
            lines.append("No sessions found.")
        buttons = [
            (f"📅  Session #{item.number} — {item.title}"[:80], f"j:s:view:{item.id}")
            for item in selected
        ]
        buttons.extend(
            [
                ("‹  Prev", f"j:s:list:{page - 1}"),
                ("Next  ›", f"j:s:list:{page + 1}"),
                ("←  Back", "j:home"),
            ]
        )
        view = _view(buttons, self._route)
        _set_enabled(view, f"j:s:list:{page - 1}", page > 0)
        _set_enabled(view, f"j:s:list:{page + 1}", page < pages - 1)
        lines.extend(["", f"Page {page + 1}/{pages}"])
        return JournalRender("\n".join(lines), view)

    def session_details(self, session_id: int, page: int) -> JournalRender:
        campaign = self.campaigns.current(self.guild_id)
        session = self.sessions.find(str(session_id), campaign.id)
        events = self.sessions.list_journal_events_for_session(session.id)
        progress = self.quests.list_for_session(session.id)
        lines = [
            f"## SESSION #{session.number}",
            f"**{session.title}**",
            "",
            f"Date: {session.played_at}",
            "",
            "**Journal Events**",
        ]
        if events:
            lines.extend(f"• {event.description}" for event in events)
        else:
            lines.append("(none)")
        lines.extend(["", "**Quest Progress**"])
        if progress:
            lines.extend(
                f"**{entry.quest_title}** — {entry.description}" for entry in progress
            )
        else:
            lines.append("(none)")
        return JournalRender(
            "\n".join(lines),
            _view((("←  Back", f"j:s:back:{page}"),), self._route),
        )

    async def _route(self, interaction: discord.Interaction, custom_id: str) -> None:
        try:
            parts = custom_id.split(":")
            action = parts[1:]
            if custom_id == "j:home":
                await _edit(interaction, self.dashboard())
            elif action[:2] == ["q", "list"]:
                await _edit(interaction, self.quest_list(action[2], int(action[3])))
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
                "✓  Confirm",
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
        )

        async def clicked(
            interaction: discord.Interaction,
            button: discord.ui.Button[discord.ui.View] = button,
        ) -> None:
            await callback(interaction, button.custom_id or "")

        cast(Any, button).callback = clicked
        view.add_item(button)
    return view


def _set_enabled(view: discord.ui.View, custom_id: str, enabled: bool) -> None:
    for item in view.children:
        if isinstance(item, discord.ui.Button) and item.custom_id == custom_id:
            item.disabled = not enabled


async def _edit(interaction: discord.Interaction, rendered: JournalRender) -> None:
    if interaction.response.is_done():
        await interaction.edit_original_response(
            content=None, embed=rendered.embed, view=rendered.view
        )
    else:
        await interaction.response.edit_message(
            content=None, embed=rendered.embed, view=rendered.view
        )


async def _error(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def _button_style(custom_id: str) -> discord.ButtonStyle:
    """Map journal actions to the semantic colors used in the reference design."""
    if custom_id in {"j:q:list:all:0", "j:s:list:0"}:
        return discord.ButtonStyle.primary
    if ":list:active:" in custom_id or ":progress:" in custom_id:
        return discord.ButtonStyle.success
    if ":complete" in custom_id or ":confirm-complete:" in custom_id:
        return discord.ButtonStyle.success
    if ":fail" in custom_id or ":confirm-fail:" in custom_id:
        return discord.ButtonStyle.danger
    return discord.ButtonStyle.secondary
