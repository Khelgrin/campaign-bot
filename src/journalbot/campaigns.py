"""Campaign domain operations and persistent guild campaign context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from journalbot.database import (
    CampaignModel,
    SessionModel,
    ServerContextModel,
    create_session_factory,
)


class CampaignError(Exception):
    """Base class for expected campaign operation errors."""


class CampaignNotFoundError(CampaignError):
    """Raised when a campaign identifier does not identify a campaign."""


class AmbiguousCampaignError(CampaignError):
    """Raised when a title identifies more than one campaign."""


class NoCampaignSelectedError(CampaignError):
    """Raised when a guild has no selected campaign."""


class CampaignHasActiveSessionError(CampaignError):
    """Raised when a campaign cannot end because a session is active."""


@dataclass(frozen=True)
class Campaign:
    """A campaign and its lifecycle state."""

    id: int
    title: str
    description: str | None
    status: str
    created_at: str
    ended_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign(model: CampaignModel) -> Campaign:
    return Campaign(
        id=model.id,
        title=model.title,
        description=model.description,
        status=model.status,
        created_at=model.created_at,
        ended_at=model.ended_at,
    )


class CampaignStore:
    """Repository for campaigns and guild-scoped current campaign context."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = database_path
        self.session_factory = create_session_factory(database_path)

    def create(
        self, guild_id: int | str, title: str, description: str | None
    ) -> Campaign:
        """Create and select a campaign atomically for a guild."""
        title = title.strip()
        if not title:
            raise ValueError("Campaign title cannot be empty.")
        timestamp = _now()
        with self.session_factory.begin() as session:
            campaign = CampaignModel(
                title=title,
                description=description or None,
                status="ACTIVE",
                created_at=timestamp,
                ended_at=None,
            )
            session.add(campaign)
            session.flush()
            self._set_context(session, guild_id, campaign, timestamp)
        return _campaign(campaign)

    def list(self) -> list[Campaign]:
        """Return all campaigns in creation order."""
        with self.session_factory() as session:
            models = session.scalars(
                select(CampaignModel).order_by(
                    CampaignModel.created_at, CampaignModel.id
                )
            ).all()
        return [_campaign(model) for model in models]

    def find(self, identifier: str) -> Campaign:
        """Find a campaign by numeric ID or exact title."""
        value = identifier.strip()
        with self.session_factory() as session:
            if value.isdigit():
                model = session.get(CampaignModel, int(value))
                models = [model] if model is not None else []
            else:
                models = list(
                    session.scalars(
                        select(CampaignModel)
                        .where(CampaignModel.title == value)
                        .order_by(CampaignModel.id)
                    ).all()
                )
        if len(models) > 1:
            raise AmbiguousCampaignError(
                "More than one campaign has that title; use its ID."
            )
        if not models:
            raise CampaignNotFoundError(f"Campaign '{identifier}' was not found.")
        return _campaign(models[0])

    def select(self, guild_id: int | str, identifier: str) -> Campaign:
        """Persist the selected campaign for a guild."""
        campaign = self.find(identifier)
        timestamp = _now()
        with self.session_factory.begin() as session:
            model = session.get(CampaignModel, campaign.id)
            if model is None:
                raise CampaignNotFoundError(f"Campaign '{identifier}' was not found.")
            self._set_context(session, guild_id, model, timestamp)
        return campaign

    def current(self, guild_id: int | str) -> Campaign:
        """Resolve the current campaign for a guild."""
        with self.session_factory() as session:
            context = session.get(ServerContextModel, str(guild_id))
            model = context.current_campaign if context is not None else None
        if model is None:
            raise NoCampaignSelectedError(
                "No campaign is currently selected. Use /use-campaign <id> first."
            )
        return _campaign(model)

    def update(
        self,
        identifier: str,
        title: str | None = None,
        description: str | None = None,
    ) -> Campaign:
        """Update campaign metadata without changing its ID."""
        campaign = self.find(identifier)
        new_title = title.strip() if title is not None else campaign.title
        if not new_title:
            raise ValueError("Campaign title cannot be empty.")
        with self.session_factory.begin() as session:
            model = session.get(CampaignModel, campaign.id)
            if model is None:
                raise CampaignNotFoundError(f"Campaign '{identifier}' was not found.")
            model.title = new_title
            if description is not None:
                model.description = description or None
        return self.find(str(campaign.id))

    def end_current(self, guild_id: int | str) -> Campaign:
        """End the currently selected campaign without deleting it."""
        campaign = self.current(guild_id)
        if campaign.status == "ENDED":
            return campaign
        with self.session_factory.begin() as session:
            model = session.get(CampaignModel, campaign.id)
            if model is None:
                raise CampaignNotFoundError(f"Campaign '{campaign.id}' was not found.")
            active_session = session.scalar(
                select(SessionModel.id).where(
                    SessionModel.campaign_id == campaign.id,
                    SessionModel.status == "ACTIVE",
                )
            )
            if active_session is not None:
                raise CampaignHasActiveSessionError(
                    "The campaign has an active session. "
                    "End the session before ending the campaign."
                )
            model.status = "ENDED"
            model.ended_at = _now()
        return self.find(str(campaign.id))

    @staticmethod
    def _set_context(
        session: OrmSession,
        guild_id: int | str,
        campaign: CampaignModel,
        timestamp: str,
    ) -> None:
        """Create or update one guild's current campaign selection."""
        context = session.get(ServerContextModel, str(guild_id))
        if context is None:
            session.add(
                ServerContextModel(
                    discord_guild_id=str(guild_id),
                    current_campaign=campaign,
                    updated_at=timestamp,
                )
            )
        else:
            if context.current_campaign_id != campaign.id:
                context.current_session = None
            context.current_campaign = campaign
            context.updated_at = timestamp
