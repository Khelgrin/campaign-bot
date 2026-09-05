"""SQLAlchemy database setup and ORM models for JournalBot."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
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
    sessions: Mapped[list["SessionModel"]] = relationship(
        back_populates="campaign"
    )


class SessionModel(Base):
    """Persistent RPG session record."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("number > 0", name="session_number_positive"),
        CheckConstraint(
            "(status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status = 'ENDED' AND ended_at IS NOT NULL)",
            name="session_lifecycle",
        ),
        UniqueConstraint("campaign_id", "number", name="uq_session_campaign_number"),
        UniqueConstraint("campaign_id", "title", name="uq_session_campaign_title"),
        Index(
            "uq_active_session_per_campaign",
            "campaign_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    played_at: Mapped[str] = mapped_column(String, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    campaign: Mapped[CampaignModel] = relationship(back_populates="sessions")
    contexts: Mapped[list["ServerContextModel"]] = relationship(
        back_populates="current_session"
    )


class ServerContextModel(Base):
    """Persistent current campaign selection for one Discord guild."""

    __tablename__ = "server_contexts"

    discord_guild_id: Mapped[str] = mapped_column(String, primary_key=True)
    current_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id"), nullable=True
    )
    current_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    current_campaign: Mapped[CampaignModel | None] = relationship(
        back_populates="contexts"
    )
    current_session: Mapped[SessionModel | None] = relationship(
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
    with engine.begin() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql(
                "PRAGMA table_info(server_contexts)"
            )
        }
        if "current_session_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE server_contexts ADD COLUMN current_session_id "
                "INTEGER REFERENCES sessions(id)"
            )
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
