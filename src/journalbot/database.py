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
    sessions: Mapped[list["SessionModel"]] = relationship(back_populates="campaign")
    quests: Mapped[list["QuestModel"]] = relationship(back_populates="campaign")


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
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
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
    quests: Mapped[list["QuestModel"]] = relationship(back_populates="started_session")
    quest_progress: Mapped[list["QuestProgressModel"]] = relationship(
        back_populates="session"
    )
    journal_events: Mapped[list["JournalEventModel"]] = relationship(
        back_populates="session"
    )


class QuestModel(Base):
    """Persistent quest record."""

    __tablename__ = "quests"
    __table_args__ = (
        CheckConstraint(
            "(status = 'ACTIVE' AND closed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'FAILED') AND closed_at IS NOT NULL)",
            name="quest_lifecycle",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    quest_giver: Mapped[str | None] = mapped_column(String, nullable=True)
    received_at_location: Mapped[str | None] = mapped_column(String, nullable=True)
    started_session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    closed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    campaign: Mapped[CampaignModel] = relationship(back_populates="quests")
    started_session: Mapped[SessionModel] = relationship(back_populates="quests")
    progress_history: Mapped[list["QuestProgressModel"]] = relationship(
        back_populates="quest"
    )


class QuestProgressModel(Base):
    """Historical record describing quest progress during one session."""

    __tablename__ = "quest_progress"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id"), nullable=False)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    quest: Mapped[QuestModel] = relationship(back_populates="progress_history")
    session: Mapped[SessionModel] = relationship(back_populates="quest_progress")


class JournalEventModel(Base):
    """Historical session-level event that is not tied to a specific quest."""

    __tablename__ = "journal_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    session: Mapped[SessionModel] = relationship(back_populates="journal_events")


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
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(server_contexts)")
        }
        if "current_session_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE server_contexts ADD COLUMN current_session_id "
                "INTEGER REFERENCES sessions(id)"
            )
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_database_url() -> str:
    """Return the database URL, preferring Postgres (DATABASE_URL) over SQLite."""
    # Check for Postgres connection string (set by Railway)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Railway provides postgres://, but SQLAlchemy needs postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    # Fall back to SQLite for local development
    configured_path = os.environ.get("JOURNALBOT_DATABASE_PATH")
    database_path = Path(configured_path) if configured_path else DEFAULT_DATABASE_PATH

    if str(database_path) != ":memory:":
        database_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{database_path.resolve().as_posix()}"
    else:
        return "sqlite:///:memory:"


def create_session_factory(database_path: str | Path = None) -> sessionmaker[Session]:
    """Create an ORM session factory and initialize the database schema."""
    # If database_path is provided, construct a SQLite URL (for backward compatibility)
    if database_path is not None:
        path = Path(database_path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{path.resolve().as_posix()}"
        else:
            url = "sqlite:///:memory:"
    else:
        # Use the environment-based URL (Postgres or SQLite)
        url = get_database_url()

    # Create engine with appropriate settings
    if url.startswith("postgresql://"):
        # Postgres-specific settings
        engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,  # Verify connections are alive
            pool_size=10,
            max_overflow=20,
        )
    else:
        # SQLite settings
        engine = create_engine(url, future=True)

    # Create all tables from models
    Base.metadata.create_all(engine)

    # Handle schema migration for current_session_id column
    with engine.begin() as connection:
        if url.startswith("postgresql://"):
            # Postgres: use information_schema
            result = connection.exec_driver_sql("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'server_contexts' AND column_name = 'current_session_id'
            """)
            column_exists = result.fetchone() is not None
        else:
            # SQLite: use PRAGMA
            result = connection.exec_driver_sql("PRAGMA table_info(server_contexts)")
            columns = {row[1] for row in result.fetchall()}
            column_exists = "current_session_id" in columns

        # Add column if it doesn't exist
        if not column_exists:
            if url.startswith("postgresql://"):
                connection.exec_driver_sql("""
                    ALTER TABLE server_contexts 
                    ADD COLUMN current_session_id INTEGER REFERENCES sessions(id)
                """)
            else:
                connection.exec_driver_sql("""
                    ALTER TABLE server_contexts 
                    ADD COLUMN current_session_id INTEGER REFERENCES sessions(id)
                """)

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
