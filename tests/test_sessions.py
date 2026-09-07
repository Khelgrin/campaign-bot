"""Tests for session persistence and lifecycle."""

from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError

from journalbot.campaigns import (
    CampaignHasActiveSessionError,
    CampaignStore,
)
from journalbot.database import (
    JournalEventModel,
    ServerContextModel,
    SessionModel,
    create_session_factory,
)
from journalbot.quests import QuestStore
from journalbot.sessions import (
    ActiveSessionExistsError,
    NoCampaignSelectedError,
    NoSessionSelectedError,
    SessionNotFoundError,
    SessionError,
    SessionStore,
)


def test_session_creation_assigns_number_and_persists_context(tmp_path) -> None:
    """
    Creating a session selects it and survives a new store instance. This exercises the
    `session creation assigns number and persists context` scenario and asserts the
    expected observable result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    campaign = CampaignStore(path).create(123, "Kingmaker", None)

    session = SessionStore(path).create(123)
    restored = SessionStore(path).current(123)

    assert session.campaign_id == campaign.id
    assert session.number == 1
    assert session.title == "Session 1"
    assert session.played_at == session.created_at
    assert restored == session


def test_selected_session_survives_a_new_store_instance(tmp_path) -> None:
    """
    Selecting a session persists the guild context across restarts. This exercises the
    `selected session survives a new store instance` scenario and asserts the expected
    observable result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    first = sessions.create(123, "Opening")
    sessions.end_current(123)
    sessions.create(123, "Finale")

    reopened = SessionStore(path)
    selected = reopened.select(123, "1")
    restored = SessionStore(path).current(123)

    assert selected.id == first.id
    assert restored == selected


def test_session_requires_current_active_campaign(tmp_path) -> None:
    """
    Session creation is attempted without a campaign and after the selected campaign has
    ended. This verifies missing context and ended-campaign context are both rejected.
    """
    store = SessionStore(tmp_path / "journalbot.sqlite3")
    with pytest.raises(NoCampaignSelectedError):
        store.create(123)

    campaigns = CampaignStore(tmp_path / "journalbot.sqlite3")
    campaigns.create(123, "Finished", None)
    campaigns.end_current(123)
    with pytest.raises(SessionError, match="campaign has ended"):
        SessionStore(tmp_path / "journalbot.sqlite3").create(123)


def test_only_one_active_session_and_campaign_end_is_guarded(tmp_path) -> None:
    """
    A campaign already has an ACTIVE session when another session is started and the
    campaign is ended. This verifies both operations are rejected until the active
    session is ended.
    """
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
    """
    A session from another campaign cannot be selected. This exercises the `session
    selection cannot switch campaign context` scenario and asserts the expected
    observable result or error.
    """
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
    """
    A session number is resolved within the current campaign first. This exercises the
    `numeric session selection stays in current campaign` scenario and asserts the
    expected observable result or error.
    """
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
    """
    A guild switches campaigns while a session from the old campaign is selected. This
    verifies the old current-session reference is cleared instead of pointing across
    campaigns.
    """
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
    """
    Metadata updates preserve identity while allowing played date correction. This
    exercises the `session update preserves id and number and corrects metadata`
    scenario and asserts the expected observable result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    created = sessions.create(
        123,
        "Opening",
        "Initial",
    )

    updated = sessions.update(
        123, str(created.id), "Revised", "Updated", "2026-09-05T18:00:00+00:00"
    )

    assert updated.id == created.id
    assert updated.number == created.number
    assert updated.title == "Revised"
    assert updated.description == "Updated"
    assert updated.played_at == "2026-09-05T18:00:00+00:00"


def test_session_requires_non_empty_title(tmp_path) -> None:
    """
    Explicit blank titles are rejected while omitted titles are generated. This
    exercises the `session requires non empty title` scenario and asserts the expected
    observable result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)

    with pytest.raises(ValueError, match="title cannot be empty"):
        sessions.create(123, "   ")


def test_session_titles_and_numbers_are_unique_per_campaign(tmp_path) -> None:
    """
    A campaign cannot contain duplicate titles or numbers. This exercises the `session
    titles and numbers are unique per campaign` scenario and asserts the expected
    observable result or error.
    """
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
    """
    The database attempts to insert session number 0 and then a second ACTIVE session in
    one campaign. This verifies positive numbering and the one-active-session constraint
    reject both invalid records.
    """
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


def test_database_requires_a_session_campaign_foreign_key(tmp_path) -> None:
    """
    The database attempts to insert a session whose `campaign_id` is null. This verifies
    the foreign-key requirement rejects orphan sessions.
    """
    path = tmp_path / "journalbot.sqlite3"
    factory = create_session_factory(path)

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                SessionModel(
                    campaign_id=cast(Any, None),
                    number=1,
                    title="Orphan",
                    description=None,
                    status="ACTIVE",
                    created_at="now",
                    played_at="now",
                    ended_at=None,
                )
            )


def test_session_can_be_selected_by_exact_title(tmp_path) -> None:
    """
    Title lookup selects the exact session in the current campaign. This exercises the
    `session can be selected by exact title` scenario and asserts the expected
    observable result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    created = SessionStore(path).create(123, "Opening")
    SessionStore(path).end_current(123)

    selected = SessionStore(path).select(123, "Opening")

    assert selected.id == created.id
    assert selected.title == created.title
    assert selected.status == "ENDED"


def test_session_update_rejects_duplicate_title(tmp_path) -> None:
    """
    Updating a title cannot collide with another session in its campaign. This exercises
    the `session update rejects duplicate title` scenario and asserts the expected
    observable result or error.
    """
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
    """
    The database attempts ACTIVE with `ended_at` filled, ENDED with `ended_at` missing,
    and an unknown status. This verifies the session lifecycle constraint rejects every
    inconsistent status/timestamp combination.
    """
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
    """
    Listing and lookup never return sessions from another campaign. This exercises the
    `session listing and lookup are scoped to current campaign` scenario and asserts the
    expected observable result or error.
    """
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
    """
    The current session is ended twice. This verifies the first call stores the terminal
    timestamp and the second call preserves the same ended record without changing its
    history.
    """
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
    """
    Session-dependent operations fail without a selected session. This exercises the
    `missing session context is explicit` scenario and asserts the expected observable
    result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)

    with pytest.raises(NoSessionSelectedError):
        SessionStore(path).current(123)


def test_session_journal_events_are_stored_and_listed_per_session(tmp_path) -> None:
    """Session-level journal events are historical and scoped to the active session."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    session = SessionStore(path).create(123, "Opening")

    event = SessionStore(path).create_journal_event(
        123,
        "The party discovered an ancient shrine beneath the ruins.",
    )

    assert event.session_id == session.id
    assert (
        event.description == "The party discovered an ancient shrine beneath the ruins."
    )
    assert [
        item.description for item in SessionStore(path).list_journal_events(123)
    ] == [event.description]

    SessionStore(path).end_current(123)
    assert [
        item.description for item in SessionStore(path).list_journal_events(123)
    ] == [event.description]


def test_journal_events_append_in_order_and_persist_across_store_instances(
    tmp_path,
) -> None:
    """Journal events preserve append-only history and survive reopening the store."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    session = sessions.create(123, "Opening")

    first = sessions.create_journal_event(123, "The party entered the ruins.")
    second = sessions.create_journal_event(123, "The party found a hidden passage.")

    reopened = SessionStore(path)
    events = reopened.list_journal_events_for_session(session.id)

    assert [event.id for event in events] == [first.id, second.id]
    assert [event.description for event in events] == [
        "The party entered the ruins.",
        "The party found a hidden passage.",
    ]


def test_journal_event_rejects_a_session_from_another_campaign(tmp_path) -> None:
    """Journal events cannot be recorded against a session in another campaign."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaign_a = campaigns.create(123, "Campaign A", None)
    sessions = SessionStore(path)
    session_a = sessions.create(123, "Session A")
    sessions.end_current(123)

    campaign_b = campaigns.create(123, "Campaign B", None)
    sessions.create(123, "Session B")

    factory = create_session_factory(path)
    with factory.begin() as db:
        context = db.get(ServerContextModel, "123")
        assert context is not None
        context.current_session_id = session_a.id

    with pytest.raises(
        ValueError,
        match="selected session does not belong to the current campaign",
    ):
        sessions.create_journal_event(123, "Cross-campaign event")

    assert campaign_a.id != campaign_b.id


def test_database_enforces_journal_event_session_foreign_key(tmp_path) -> None:
    """JournalEvent cannot reference a missing Session."""
    path = tmp_path / "journalbot.sqlite3"
    factory = create_session_factory(path)

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                JournalEventModel(
                    session_id=999,
                    description="Invalid session reference",
                    created_at="now",
                )
            )


def test_historical_records_survive_parent_updates_and_closure(tmp_path) -> None:
    """Parent metadata and lifecycle changes do not overwrite historical records."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    session = sessions.create(123, "Opening", "Original session notes")
    event = sessions.create_journal_event(123, "The party found a shrine.")

    quest = QuestStore(path).create(123, "Find the Merchant")
    progress = QuestStore(path).create_progress(
        123, str(quest.id), "Found the merchant's cart."
    )

    sessions.update(123, str(session.id), "Revised opening", "Updated notes")
    sessions.end_current(123)
    QuestStore(path).complete(123, str(quest.id))

    reopened_sessions = SessionStore(path)
    reopened_quests = QuestStore(path)
    assert reopened_sessions.list_journal_events_for_session(session.id)[0] == event
    assert reopened_quests.list_progress(123, str(quest.id))[0] == progress
