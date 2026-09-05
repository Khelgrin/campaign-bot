"""Session domain operations and persistent guild session context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from journalbot.campaigns import NoCampaignSelectedError
from journalbot.database import SessionModel, ServerContextModel, create_session_factory


class SessionError(Exception):
    """Base class for expected session operation errors."""


class SessionNotFoundError(SessionError):
    """Raised when a session identifier does not identify a session."""


class AmbiguousSessionError(SessionError):
    """Raised when a session title is not unique in its campaign."""


class NoSessionSelectedError(SessionError):
    """Raised when a guild has no selected session."""


class ActiveSessionExistsError(SessionError):
    """Raised when a campaign already has an active session."""


@dataclass(frozen=True)
class Session:
    """An RPG session and its lifecycle state."""

    id: int
    campaign_id: int
    number: int
    title: str
    description: str | None
    status: str
    created_at: str
    played_at: str
    ended_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session(model: SessionModel) -> Session:
    return Session(
        id=model.id,
        campaign_id=model.campaign_id,
        number=model.number,
        title=model.title,
        description=model.description,
        status=model.status,
        created_at=model.created_at,
        played_at=model.played_at,
        ended_at=model.ended_at,
    )


class SessionStore:
    """Repository for sessions and guild-scoped current session context."""

    def __init__(self, database_path: str | Path) -> None:
        self.session_factory = create_session_factory(database_path)

    def create(
        self,
        guild_id: int | str,
        title: str | None = None,
        description: str | None = None,
    ) -> Session:
        """Create and select an active session for the current campaign."""
        timestamp = _now()
        with self.session_factory.begin() as session:
            context = session.get(ServerContextModel, str(guild_id))
            campaign = (
                context.current_campaign if context is not None else None
            )
            if campaign is None or context is None:
                raise NoCampaignSelectedError(
                    "No campaign is currently selected. "
                    "Use !use-campaign <id or title> first."
                )
            if campaign.status == "ENDED":
                raise SessionError(
                    "The selected campaign has ended. "
                    "Select an active campaign first."
                )
            active = session.scalar(
                select(SessionModel.id).where(
                    SessionModel.campaign_id == campaign.id,
                    SessionModel.status == "ACTIVE",
                )
            )
            if active is not None:
                raise ActiveSessionExistsError(
                    "The campaign already has an active session. "
                    "End it before starting another."
                )
            last_number = session.scalar(
                select(SessionModel.number)
                .where(SessionModel.campaign_id == campaign.id)
                .order_by(SessionModel.number.desc())
                .limit(1)
            )
            number = (last_number or 0) + 1
            clean_title = (title or f"Session {number}").strip()
            if not clean_title:
                raise ValueError("Session title cannot be empty.")
            duplicate_title = session.scalar(
                select(SessionModel.id).where(
                    SessionModel.campaign_id == campaign.id,
                    SessionModel.title == clean_title,
                )
            )
            if duplicate_title is not None:
                raise ValueError("A session with that title already exists.")
            model = SessionModel(
                campaign=campaign,
                number=number,
                title=clean_title,
                description=description or None,
                status="ACTIVE",
                created_at=timestamp,
                played_at=timestamp,
                ended_at=None,
            )
            session.add(model)
            session.flush()
            context.current_session = model
            context.updated_at = timestamp
        return _session(model)

    def list_current_campaign(self, guild_id: int | str) -> list[Session]:
        """List sessions belonging to the current campaign."""
        campaign = self._current_campaign_id(guild_id)
        with self.session_factory() as session:
            models = session.scalars(
                select(SessionModel)
                .where(SessionModel.campaign_id == campaign)
                .order_by(SessionModel.number)
            ).all()
        return [_session(model) for model in models]

    def find(self, identifier: str, campaign_id: int) -> Session:
        """Find a session by ID or exact title within a campaign."""
        value = identifier.strip()
        with self.session_factory() as session:
            if value.isdigit():
                models = list(
                    session.scalars(
                        select(SessionModel).where(
                            SessionModel.id == int(value),
                            SessionModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
            else:
                models = list(
                    session.scalars(
                        select(SessionModel).where(
                            SessionModel.title == value,
                            SessionModel.campaign_id == campaign_id,
                        )
                    ).all()
                )
        if len(models) > 1:
            raise AmbiguousSessionError(
                "More than one session has that title; use its ID."
            )
        if not models:
            raise SessionNotFoundError(f"Session '{identifier}' was not found.")
        return _session(models[0])

    def select(self, guild_id: int | str, identifier: str) -> Session:
        """Select a session and make its campaign current."""
        with self.session_factory.begin() as session:
            context = session.get(ServerContextModel, str(guild_id))
            value = identifier.strip()
            if value.isdigit():
                model = session.get(SessionModel, int(value))
            else:
                if context is None or context.current_campaign_id is None:
                    raise NoCampaignSelectedError(
                        "No campaign is currently selected. "
                        "Use !use-campaign <id or title> first."
                    )
                model = session.scalar(
                    select(SessionModel).where(
                        SessionModel.title == value,
                        SessionModel.campaign_id == context.current_campaign_id,
                    )
                )
            if model is None:
                raise SessionNotFoundError(
                    f"Session '{identifier}' was not found."
                )
            if context is None:
                context = ServerContextModel(
                    discord_guild_id=str(guild_id),
                    updated_at=_now(),
                )
                session.add(context)
            context.current_campaign = model.campaign
            context.current_session = model
            context.updated_at = _now()
        return _session(model)

    def current(self, guild_id: int | str) -> Session:
        """Resolve the current session for a guild."""
        with self.session_factory() as session:
            context = session.get(ServerContextModel, str(guild_id))
            model = context.current_session if context is not None else None
        if model is None:
            raise NoSessionSelectedError(
                "No session is currently selected. "
                "Use !use-session <id or title> first."
            )
        return _session(model)

    def update(
        self,
        guild_id: int | str,
        identifier: str,
        title: str | None = None,
        description: str | None = None,
        played_at: str | None = None,
    ) -> Session:
        """Update session metadata without changing its identity."""
        campaign_id = self._current_campaign_id(guild_id)
        found = self.find(identifier, campaign_id)
        with self.session_factory.begin() as session:
            model = session.get(SessionModel, found.id)
            if model is None:
                raise SessionNotFoundError(
                    f"Session '{identifier}' was not found."
                )
            if title is not None:
                new_title = title.strip()
                if not new_title:
                    raise ValueError("Session title cannot be empty.")
                duplicate_title = session.scalar(
                    select(SessionModel.id).where(
                        SessionModel.campaign_id == campaign_id,
                        SessionModel.title == new_title,
                        SessionModel.id != found.id,
                    )
                )
                if duplicate_title is not None:
                    raise ValueError("A session with that title already exists.")
                model.title = new_title
            if description is not None:
                model.description = description or None
            if played_at is not None:
                model.played_at = played_at
        return self.find(str(found.id), campaign_id)

    def end_current(self, guild_id: int | str) -> Session:
        """End the selected session, retaining its record."""
        current = self.current(guild_id)
        if current.status == "ENDED":
            return current
        with self.session_factory.begin() as session:
            model = session.get(SessionModel, current.id)
            if model is None:
                raise SessionNotFoundError(
                    f"Session '{current.id}' was not found."
                )
            model.status = "ENDED"
            model.ended_at = _now()
        return self.current(guild_id)

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
