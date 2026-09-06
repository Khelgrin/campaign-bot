"""Quest domain operations and helper methods for current campaign context."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from journalbot.campaigns import NoCampaignSelectedError
from journalbot.database import (
    CampaignModel,
    QuestModel,
    QuestProgressModel,
    ServerContextModel,
    create_session_factory,
)
from journalbot.sessions import NoSessionSelectedError


class QuestError(Exception):
    """Base class for expected quest operation errors."""


class QuestNotFoundError(QuestError):
    """Raised when a quest identifier does not identify a quest."""


class AmbiguousQuestError(QuestError):
    """Raised when a quest title is not unique within its campaign."""


class QuestProgressError(QuestError):
    """Base class for expected quest-progress operation errors."""


@dataclass(frozen=True)
class Quest:
    """A quest and its current lifecycle state."""

    id: int
    campaign_id: int
    title: str
    description: str | None
    quest_giver: str | None
    received_at_location: str | None
    started_session_id: int
    status: str
    created_at: str
    closed_at: str | None


@dataclass(frozen=True)
class QuestProgress:
    """A historical progress entry for a quest."""

    id: int
    quest_id: int
    session_id: int
    description: str
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quest(model: QuestModel) -> Quest:
    return Quest(
        id=model.id,
        campaign_id=model.campaign_id,
        title=model.title,
        description=model.description,
        quest_giver=model.quest_giver,
        received_at_location=model.received_at_location,
        started_session_id=model.started_session_id,
        status=model.status,
        created_at=model.created_at,
        closed_at=model.closed_at,
    )


def _quest_progress(model: QuestProgressModel) -> QuestProgress:
    return QuestProgress(
        id=model.id,
        quest_id=model.quest_id,
        session_id=model.session_id,
        description=model.description,
        created_at=model.created_at,
    )


class QuestProgressStore:
    """Repository for historical quest progress entries."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(Path(database_path))
        self.session_factory = create_session_factory(database_path)

    def create(
        self,
        guild_id: int | str,
        quest_identifier: str,
        description: str,
    ) -> QuestProgress:
        """Create a new historical progress record for the selected quest."""
        clean_description = (description or "").strip()
        if not clean_description:
            raise ValueError("Quest progress description cannot be empty.")

        with self.session_factory.begin() as session:
            context = session.get(ServerContextModel, str(guild_id))
            campaign_id = (
                context.current_campaign_id if context is not None else None
            )
            if campaign_id is None:
                raise NoCampaignSelectedError(
                    "No campaign is currently selected. "
                    "Use !use-campaign <id or title> first."
                )
            current_session = context.current_session if context is not None else None
            if current_session is None:
                raise NoSessionSelectedError(
                    "No session is currently selected. "
                    "Use !use-session <id or title> first."
                )
            if current_session.campaign_id != campaign_id:
                raise ValueError(
                    "The selected session does not belong to the current campaign."
                )

            value = quest_identifier.strip()
            if value.isdigit():
                models = list(
                    session.scalars(
                        select(QuestModel).where(
                            QuestModel.id == int(value),
                            QuestModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
            else:
                models = list(
                    session.scalars(
                        select(QuestModel).where(
                            QuestModel.title == value,
                            QuestModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
            if len(models) > 1:
                raise AmbiguousQuestError(
                    "More than one quest has that title; use its ID."
                )
            if not models:
                raise QuestNotFoundError(
                    f"Quest '{quest_identifier}' was not found."
                )
            quest_model = models[0]
            if quest_model.status != "ACTIVE":
                raise ValueError(
                    "Progress can only be added to an ACTIVE quest."
                )

            model = QuestProgressModel(
                quest_id=quest_model.id,
                session_id=current_session.id,
                description=clean_description,
                created_at=_now(),
            )
            session.add(model)
            session.flush()
        return _quest_progress(model)

    def list_for_quest(
        self,
        guild_id: int | str,
        quest_identifier: str,
    ) -> Sequence[QuestProgress]:
        """Return the historical progress entries for a quest in the campaign."""
        with self.session_factory() as session:
            context = session.get(ServerContextModel, str(guild_id))
            if context is None or context.current_campaign_id is None:
                raise NoCampaignSelectedError(
                    "No campaign is currently selected. "
                    "Use !use-campaign <id or title> first."
                )
            campaign_id = context.current_campaign_id
            value = quest_identifier.strip()
            if value.isdigit():
                models = list(
                    session.scalars(
                        select(QuestModel).where(
                            QuestModel.id == int(value),
                            QuestModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
            else:
                models = list(
                    session.scalars(
                        select(QuestModel).where(
                            QuestModel.title == value,
                            QuestModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
            if len(models) > 1:
                raise AmbiguousQuestError(
                    "More than one quest has that title; use its ID."
                )
            if not models:
                raise QuestNotFoundError(
                    f"Quest '{quest_identifier}' was not found."
                )
            quest_model = models[0]
            progress_models = session.scalars(
                select(QuestProgressModel)
                .where(QuestProgressModel.quest_id == quest_model.id)
                .order_by(QuestProgressModel.created_at, QuestProgressModel.id)
            ).all()
        return [_quest_progress(model) for model in progress_models]

    def list_by_quest(
        self,
        guild_id: int | str,
        quest_identifier: str,
    ) -> Sequence[QuestProgress]:
        """Alias for listing quest progress entries."""
        return self.list_for_quest(guild_id, quest_identifier)


class QuestStore:
    """Repository for quests and current campaign-scoped quest queries."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(Path(database_path))
        self.session_factory = create_session_factory(database_path)

    def create(
        self,
        guild_id: int | str,
        title: str,
        description: str | None = None,
        quest_giver: str | None = None,
        received_at_location: str | None = None,
    ) -> Quest:
        """Create a new active quest for the current campaign and session."""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Quest title cannot be empty.")
        timestamp = _now()
        with self.session_factory.begin() as session:
            context = session.get(ServerContextModel, str(guild_id))
            campaign_id = (
                context.current_campaign_id if context is not None else None
            )
            if campaign_id is None:
                raise NoCampaignSelectedError(
                    "No campaign is currently selected. "
                    "Use !use-campaign <id or title> first."
                )
            campaign = session.get(CampaignModel, campaign_id)
            if campaign is None:
                raise NoCampaignSelectedError(
                    "No campaign is currently selected. "
                    "Use !use-campaign <id or title> first."
                )
            current_session = context.current_session if context is not None else None
            if current_session is None:
                raise NoSessionSelectedError(
                    "No session is currently selected. "
                    "Use !use-session <id or title> first."
                )
            if current_session.campaign_id != campaign_id:
                raise ValueError(
                    "The selected session does not belong to the current campaign."
                )
            model = QuestModel(
                campaign_id=campaign_id,
                title=clean_title,
                description=(description.strip() if description is not None else None)
                or None,
                quest_giver=(quest_giver.strip() if quest_giver is not None else None)
                or None,
                received_at_location=(
                    received_at_location.strip()
                    if received_at_location is not None
                    else None
                )
                or None,
                started_session_id=current_session.id,
                status="ACTIVE",
                created_at=timestamp,
                closed_at=None,
            )
            session.add(model)
            session.flush()
        return _quest(model)

    def list(self, guild_id: int | str, status: str = "all") -> Sequence[Quest]:
        """List quests for the current campaign, optionally filtered by lifecycle."""
        campaign_id = self._current_campaign_id(guild_id)
        normalized = (status or "all").strip().lower()
        query = select(QuestModel).where(QuestModel.campaign_id == campaign_id)
        if normalized == "active":
            query = query.where(QuestModel.status == "ACTIVE")
        elif normalized == "completed":
            query = query.where(QuestModel.status == "COMPLETED")
        elif normalized == "failed":
            query = query.where(QuestModel.status == "FAILED")
        elif normalized == "finished":
            query = query.where(QuestModel.status.in_(["COMPLETED", "FAILED"]))
        elif normalized in {"all", ""}:
            pass
        else:
            raise ValueError(f"Unknown quest status filter: {status!r}")
        with self.session_factory() as session:
            models = session.scalars(
                query.order_by(QuestModel.created_at, QuestModel.id)
            ).all()
        return [_quest(model) for model in models]

    def list_current_campaign(
        self, guild_id: int | str, status: str = "all"
    ) -> Sequence[Quest]:
        """Backward-compatible alias for listing the current campaign's quests."""
        return self.list(guild_id, status=status)

    def find(self, identifier: str, campaign_id: int) -> Quest:
        """Find a quest by numeric ID or exact title within the current campaign."""
        value = identifier.strip()
        with self.session_factory() as session:
            if value.isdigit():
                models = list(
                    session.scalars(
                        select(QuestModel).where(
                            QuestModel.id == int(value),
                            QuestModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
            else:
                models = list(
                    session.scalars(
                        select(QuestModel).where(
                            QuestModel.title == value,
                            QuestModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
        if len(models) > 1:
            raise AmbiguousQuestError(
                "More than one quest has that title; use its ID."
            )
        if not models:
            raise QuestNotFoundError(f"Quest '{identifier}' was not found.")
        return _quest(models[0])

    def update(
        self,
        guild_id: int | str,
        identifier: str,
        title: str | None = None,
        description: str | None = None,
        quest_giver: str | None = None,
        received_at_location: str | None = None,
    ) -> Quest:
        """Update quest metadata without changing identity or lifecycle."""
        campaign_id = self._current_campaign_id(guild_id)
        found = self.find(identifier, campaign_id)
        with self.session_factory.begin() as session:
            model = session.get(QuestModel, found.id)
            if model is None or model.campaign_id != campaign_id:
                raise QuestNotFoundError(f"Quest '{identifier}' was not found.")
            if title is not None:
                clean_title = title.strip()
                if not clean_title:
                    raise ValueError("Quest title cannot be empty.")
                model.title = clean_title
            if description is not None:
                model.description = description.strip() or None
            if quest_giver is not None:
                model.quest_giver = quest_giver.strip() or None
            if received_at_location is not None:
                model.received_at_location = received_at_location.strip() or None
        return self.find(str(found.id), campaign_id)

    def complete(self, guild_id: int | str, identifier: str) -> Quest:
        """Mark a quest as completed and retain its historical record."""
        campaign_id = self._current_campaign_id(guild_id)
        quest = self.find(identifier, campaign_id)
        if quest.status == "COMPLETED":
            return quest
        with self.session_factory.begin() as session:
            model = session.get(QuestModel, quest.id)
            if model is None or model.campaign_id != campaign_id:
                raise QuestNotFoundError(f"Quest '{identifier}' was not found.")
            model.status = "COMPLETED"
            model.closed_at = _now()
        return self.find(str(quest.id), campaign_id)

    def fail(self, guild_id: int | str, identifier: str) -> Quest:
        """Mark a quest as failed and retain its historical record."""
        campaign_id = self._current_campaign_id(guild_id)
        quest = self.find(identifier, campaign_id)
        if quest.status == "FAILED":
            return quest
        with self.session_factory.begin() as session:
            model = session.get(QuestModel, quest.id)
            if model is None or model.campaign_id != campaign_id:
                raise QuestNotFoundError(f"Quest '{identifier}' was not found.")
            model.status = "FAILED"
            model.closed_at = _now()
        return self.find(str(quest.id), campaign_id)

    def create_progress(
        self,
        guild_id: int | str,
        identifier: str,
        description: str,
    ) -> QuestProgress:
        """Add historical progress to a quest in the current guild session."""
        return QuestProgressStore(self.database_path).create(
            guild_id, identifier, description
        )

    def add_progress(
        self,
        guild_id: int | str,
        identifier: str,
        description: str,
    ) -> QuestProgress:
        """Alias for creating a new progress record."""
        return self.create_progress(guild_id, identifier, description)

    def progress(
        self,
        guild_id: int | str,
        identifier: str,
        description: str,
    ) -> QuestProgress:
        """Alias for progress creation."""
        return self.create_progress(guild_id, identifier, description)

    def list_progress(
        self,
        guild_id: int | str,
        identifier: str,
    ) -> Sequence[QuestProgress]:
        """Return the historical progress entries for a quest."""
        return QuestProgressStore(self.database_path).list_for_quest(
            guild_id, identifier
        )

    def progress_history(
        self,
        guild_id: int | str,
        identifier: str,
    ) -> Sequence[QuestProgress]:
        """Alias for listing a quest's progress history."""
        return self.list_progress(guild_id, identifier)

    def _current_campaign_id(self, guild_id: int | str) -> int:
        with self.session_factory() as session:
            context = session.get(ServerContextModel, str(guild_id))
            campaign_id = (
                context.current_campaign_id if context is not None else None
            )
        if campaign_id is None:
            raise NoCampaignSelectedError(
                "No campaign is currently selected. "
                "Use !use-campaign <id or title> first."
            )
        return campaign_id
