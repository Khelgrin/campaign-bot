"""Tests for session persistence and lifecycle."""

import pytest
from sqlalchemy.exc import IntegrityError

from journalbot.campaigns import (
    CampaignHasActiveSessionError,
    CampaignStore,
)
from journalbot.database import SessionModel, create_session_factory
from journalbot.sessions import (
    ActiveSessionExistsError,
    NoCampaignSelectedError,
    NoSessionSelectedError,
    SessionNotFoundError,
    SessionError,
    SessionStore,
)


def test_session_creation_assigns_number_and_persists_context(tmp_path) -> None:
    """Creating a session selects it and survives a new store instance."""
    path = tmp_path / "journalbot.sqlite3"
    campaign = CampaignStore(path).create(123, "Kingmaker", None)

    session = SessionStore(path).create(123)
    restored = SessionStore(path).current(123)

    assert session.campaign_id == campaign.id
    assert session.number == 1
    assert session.title == "Session 1"
    assert session.played_at == session.created_at
    assert restored == session


def test_session_requires_current_active_campaign(tmp_path) -> None:
    """Session creation reports missing and ended campaign context."""
    store = SessionStore(tmp_path / "journalbot.sqlite3")
    with pytest.raises(NoCampaignSelectedError):
        store.create(123)

    campaigns = CampaignStore(tmp_path / "journalbot.sqlite3")
    campaigns.create(123, "Finished", None)
    campaigns.end_current(123)
    with pytest.raises(SessionError, match="campaign has ended"):
        SessionStore(tmp_path / "journalbot.sqlite3").create(123)


def test_only_one_active_session_and_campaign_end_is_guarded(tmp_path) -> None:
    """An active session blocks both another session and campaign ending."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    sessions.create(123, "Opening")

    with pytest.raises(ActiveSessionExistsError):
        sessions.create(123, "Second")
    with pytest.raises(CampaignHasActiveSessionError):
        campaigns.end_current(123)

    ended = sessions.end_current(123)
    assert ended.status == "ENDED"
    assert campaigns.end_current(123).status == "ENDED"


def test_session_selection_cannot_switch_campaign_context(tmp_path) -> None:
    """A session from another campaign cannot be selected."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "First", None)
    first_session = SessionStore(path).create(123, "First session")
    campaigns.create(123, "Second", None)
    second_session = SessionStore(path).create(123, "Second session")

    sessions = SessionStore(path)
    with pytest.raises(SessionNotFoundError):
        sessions.select(123, f"id:{first_session.id}")

    assert campaigns.current(123).title == "Second"
    assert sessions.current(123).id == second_session.id
    assert first_session.campaign_id != second_session.campaign_id


def test_numeric_session_selection_stays_in_current_campaign(tmp_path) -> None:
    """A session number is resolved within the current campaign first."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    first = campaigns.create(123, "First", None)
    first_session = SessionStore(path).create(123, "First session")
    SessionStore(path).end_current(123)
    campaigns.create(123, "Second", None)
    second_session = SessionStore(path).create(123, "Second session")

    sessions = SessionStore(path)
    selected_by_number = sessions.select(123, "1")

    assert selected_by_number.id == second_session.id
    assert selected_by_number.campaign_id != first.id
    with pytest.raises(SessionNotFoundError):
        sessions.select(123, f"id:{first_session.id}")


def test_switching_campaign_clears_session_from_previous_campaign(tmp_path) -> None:
    """Campaign selection cannot leave a session from another campaign current."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    first = campaigns.create(123, "First", None)
    first_session = SessionStore(path).create(123, "First session")

    second = campaigns.create(123, "Second", None)

    assert campaigns.current(123).id == second.id
    with pytest.raises(NoSessionSelectedError):
        SessionStore(path).current(123)
    assert first_session.campaign_id == first.id


def test_session_update_preserves_id_and_number_and_corrects_metadata(tmp_path) -> None:
    """Metadata updates preserve identity while allowing played date correction."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    created = sessions.create(123, "Opening", "Initial",)

    updated = sessions.update(
        123, str(created.id), "Revised", "Updated", "2026-09-05T18:00:00+00:00"
    )

    assert updated.id == created.id
    assert updated.number == created.number
    assert updated.title == "Revised"
    assert updated.description == "Updated"
    assert updated.played_at == "2026-09-05T18:00:00+00:00"


def test_session_requires_non_empty_title(tmp_path) -> None:
    """Explicit blank titles are rejected while omitted titles are generated."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)

    with pytest.raises(ValueError, match="title cannot be empty"):
        sessions.create(123, "   ")


def test_session_titles_and_numbers_are_unique_per_campaign(tmp_path) -> None:
    """A campaign cannot contain duplicate titles or numbers."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaign = campaigns.create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    first = sessions.create(123, "Opening")
    sessions.end_current(123)

    with pytest.raises(ValueError, match="title already exists"):
        sessions.create(123, "Opening")

    factory = create_session_factory(path)
    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                SessionModel(
                    campaign_id=campaign.id,
                    number=first.number,
                    title="Different",
                    description=None,
                    status="ENDED",
                    created_at="now",
                    played_at="now",
                    ended_at="later",
                )
            )


def test_database_enforces_positive_session_numbers_and_one_active_session(
    tmp_path,
) -> None:
    """The schema rejects non-positive numbers and duplicate active sessions."""
    path = tmp_path / "journalbot.sqlite3"
    campaign = CampaignStore(path).create(123, "Kingmaker", None)
    factory = create_session_factory(path)

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                SessionModel(
                    campaign_id=campaign.id,
                    number=0,
                    title="Invalid number",
                    description=None,
                    status="ENDED",
                    created_at="now",
                    played_at="now",
                    ended_at="later",
                )
            )

    with factory.begin() as db:
        db.add(
            SessionModel(
                campaign_id=campaign.id,
                number=1,
                title="First",
                description=None,
                status="ACTIVE",
                created_at="now",
                played_at="now",
                ended_at=None,
            )
        )
    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                SessionModel(
                    campaign_id=campaign.id,
                    number=2,
                    title="Second",
                    description=None,
                    status="ACTIVE",
                    created_at="now",
                    played_at="now",
                    ended_at=None,
                )
            )


def test_session_can_be_selected_by_exact_title(tmp_path) -> None:
    """Title lookup selects the exact session in the current campaign."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    created = SessionStore(path).create(123, "Opening")
    SessionStore(path).end_current(123)

    selected = SessionStore(path).select(123, "Opening")

    assert selected.id == created.id
    assert selected.title == created.title
    assert selected.status == "ENDED"


def test_session_update_rejects_duplicate_title(tmp_path) -> None:
    """Updating a title cannot collide with another session in its campaign."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    first = sessions.create(123, "Opening")
    sessions.end_current(123)
    second = sessions.create(123, "Finale")

    with pytest.raises(ValueError, match="title already exists"):
        sessions.update(123, str(second.id), "Opening")

    assert sessions.find(str(first.id), first.campaign_id).title == "Opening"


@pytest.mark.parametrize(
    ("status", "ended_at"),
    [("ACTIVE", "should be null"), ("ENDED", None), ("OTHER", None)],
)
def test_database_enforces_session_lifecycle(
    tmp_path, status: str, ended_at: str | None
) -> None:
    """The schema rejects invalid session lifecycle state."""
    path = tmp_path / "journalbot.sqlite3"
    campaign = CampaignStore(path).create(123, "Kingmaker", None)
    factory = create_session_factory(path)

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                SessionModel(
                    campaign_id=campaign.id,
                    number=1,
                    title="Invalid",
                    description=None,
                    status=status,
                    created_at="now",
                    played_at="now",
                    ended_at=ended_at,
                )
            )


def test_session_listing_and_lookup_are_scoped_to_current_campaign(tmp_path) -> None:
    """Listing and lookup never return sessions from another campaign."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    first = campaigns.create(123, "First", None)
    sessions = SessionStore(path)
    first_session = sessions.create(123, "First session")
    sessions.end_current(123)
    second = campaigns.create(123, "Second", None)
    second_session = sessions.create(123, "Second session")

    assert [item.id for item in sessions.list_current_campaign(123)] == [
        second_session.id
    ]
    with pytest.raises(SessionNotFoundError):
        sessions.find(str(first_session.id), second.id)
    assert first_session.campaign_id == first.id


def test_ending_session_preserves_record_and_is_idempotent(tmp_path) -> None:
    """Ending retains timestamps and repeated ending leaves the state unchanged."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    created = sessions.create(123, "Opening")

    ended = sessions.end_current(123)
    repeated = sessions.end_current(123)

    assert ended.id == created.id
    assert ended.created_at == created.created_at
    assert ended.played_at == created.played_at
    assert ended.ended_at is not None
    assert repeated == ended
    assert sessions.find(str(created.id), created.campaign_id) == ended


def test_missing_session_context_is_explicit(tmp_path) -> None:
    """Session-dependent operations fail without a selected session."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)

    with pytest.raises(NoSessionSelectedError):
        SessionStore(path).current(123)
