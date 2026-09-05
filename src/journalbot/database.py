"""SQLAlchemy database setup and ORM models for JournalBot."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKey, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_PATH = Path("data") / "journalbot.sqlite3"


class Base(DeclarativeBase):
    """Base class for JournalBot ORM models."""


class CampaignModel(Base):
    """Persistent campaign record."""

    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "(status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status = 'ENDED' AND ended_at IS NOT NULL)",
            name="campaign_lifecycle",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    contexts: Mapped[list["ServerContextModel"]] = relationship(
        back_populates="current_campaign"
    )


class ServerContextModel(Base):
    """Persistent current campaign selection for one Discord guild."""

    __tablename__ = "server_contexts"

    discord_guild_id: Mapped[str] = mapped_column(String, primary_key=True)
    current_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id"), nullable=True
    )
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    current_campaign: Mapped[CampaignModel | None] = relationship(
        back_populates="contexts"
    )


def get_database_path() -> Path:
    """Return the configured database path, defaulting to local persistent storage."""
    configured_path = os.environ.get("JOURNALBOT_DATABASE_PATH")
    return Path(configured_path) if configured_path else DEFAULT_DATABASE_PATH


def create_session_factory(database_path: str | Path) -> sessionmaker[Session]:
    """Create an ORM session factory and initialize the database schema."""
    path = Path(database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path.resolve().as_posix()}"
    else:
        url = "sqlite:///:memory:"

    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(
    dbapi_connection: object, connection_record: object
) -> None:
    """Enable SQLite foreign-key enforcement for every ORM connection."""
    del connection_record
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
