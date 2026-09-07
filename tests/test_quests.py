"""Tests for quest persistence and lifecycle."""

import pytest
from sqlalchemy.exc import IntegrityError

from journalbot.campaigns import CampaignStore
from journalbot.database import (
    QuestProgressModel,
    QuestModel,
    ServerContextModel,
    create_session_factory,
)
from journalbot.quests import (
    AmbiguousQuestError,
    QuestNotFoundError,
    QuestProgressStore,
    QuestStore,
)
from journalbot.sessions import SessionStore


def test_quest_creation_requires_active_campaign_and_session(tmp_path) -> None:
    """
    Quest creation is attempted with no campaign, with a campaign but no session, and
    finally with both selected. This verifies each required context is enforced and the
    successful quest starts ACTIVE in the selected session.
    """
    path = tmp_path / "journalbot.sqlite3"
    store = QuestStore(path)

    with pytest.raises(Exception):
        store.create(123, "Rescue the Merchant")

    CampaignStore(path).create(123, "Kingmaker", None)
    with pytest.raises(Exception):
        store.create(123, "Rescue the Merchant")

    SessionStore(path).create(123, "Session 1")
    quest = store.create(123, "Rescue the Merchant", "Find the missing merchant.")
    assert quest.status == "ACTIVE"
    assert quest.started_session_id > 0


def test_quest_creation_rejects_session_from_another_campaign(tmp_path) -> None:
    """Quest creation rejects a current session that belongs to another campaign."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    sessions = SessionStore(path)
    quests = QuestStore(path)

    campaign_a = campaigns.create(123, "Campaign A", None)
    session_a = sessions.create(123, "Session A")
    sessions.end_current(123)

    campaign_b = campaigns.create(123, "Campaign B", None)
    session_b = sessions.create(123, "Session B")
    sessions.end_current(123)

    campaigns.select(123, str(campaign_a.id))
    factory = create_session_factory(path)
    with factory.begin() as db:
        context = db.get(ServerContextModel, "123")
        assert context is not None
        context.current_session_id = session_b.id

    with pytest.raises(
        ValueError,
        match="selected session does not belong to the current campaign",
    ):
        quests.create(123, "Cross-Campaign Quest")

    assert quests.list(123) == []
    assert session_a.campaign_id == campaign_a.id
    assert campaign_b.id != campaign_a.id


def test_quest_update_and_completion_keep_identity_and_history(tmp_path) -> None:
    """
    A quest is updated, completed, and then failed through the store. This verifies
    metadata updates preserve identity while terminal transitions set the corresponding
    status and closing timestamp.
    """
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    SessionStore(path).create(123, "Session 1")

    created = QuestStore(path).create(
        123,
        "Find the Merchant",
        "Find the merchant.",
        "Mayor Menhemes",
        "Otari Town Hall",
    )
    updated = QuestStore(path).update(
        123,
        str(created.id),
        "Find the Missing Merchant",
        "Find the missing merchant.",
        "Mayor Menhemes",
        "Otari Town Hall",
    )

    assert updated.id == created.id
    assert updated.title == "Find the Missing Merchant"
    assert updated.description == "Find the missing merchant."

    completed = QuestStore(path).complete(123, str(updated.id))
    assert completed.status == "COMPLETED"
    assert completed.closed_at is not None

    failed = QuestStore(path).fail(123, str(updated.id))
    assert failed.status == "FAILED"
    assert failed.closed_at is not None


def test_quest_lookup_is_campaign_scoped_and_ambiguous_titles_are_rejected(
    tmp_path,
) -> None:
    """
    The same quest title can recur across campaigns but not within one campaign. This
    exercises the `quest lookup is campaign scoped and ambiguous titles are rejected`
    scenario and asserts the expected observable result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "Campaign A", None)
    SessionStore(path).create(123, "Session 1")
    first = QuestStore(path).create(123, "Escort the Merchant")

    campaigns.create(123, "Campaign B", None)
    SessionStore(path).create(123, "Session 1")
    second = QuestStore(path).create(123, "Escort the Merchant")

    assert (
        QuestStore(path).find(str(first.id), campaigns.find("Campaign A").id) == first
    )
    assert (
        QuestStore(path).find(str(second.id), campaigns.find("Campaign B").id) == second
    )

    SessionStore(path).end_current(123)
    CampaignStore(path).select(123, "Campaign A")
    SessionStore(path).select(123, "1")
    SessionStore(path).end_current(123)
    SessionStore(path).create(123, "Session 2")
    QuestStore(path).create(123, "Escort the Merchant")
    with pytest.raises(AmbiguousQuestError):
        QuestStore(path).find("Escort the Merchant", campaigns.find("Campaign A").id)


def test_database_enforces_quest_lifecycle_invariants(tmp_path) -> None:
    """
    The database attempts to store an ACTIVE quest with `closed_at` filled and a
    COMPLETED quest with `closed_at` missing. This verifies the `quest_lifecycle`
    constraint rejects both invalid status/timestamp combinations.
    """
    path = tmp_path / "journalbot.sqlite3"
    campaign = CampaignStore(path).create(123, "Kingmaker", None)
    session = SessionStore(path).create(123, "Session 1")
    factory = create_session_factory(path)

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                QuestModel(
                    campaign_id=campaign.id,
                    title="Invalid",
                    description=None,
                    quest_giver=None,
                    received_at_location=None,
                    started_session_id=session.id,
                    status="ACTIVE",
                    created_at="now",
                    closed_at="later",
                )
            )

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                QuestModel(
                    campaign_id=campaign.id,
                    title="Invalid",
                    description=None,
                    quest_giver=None,
                    received_at_location=None,
                    started_session_id=session.id,
                    status="COMPLETED",
                    created_at="now",
                    closed_at=None,
                )
            )


def test_quest_status_filter_uses_campaign_context(tmp_path) -> None:
    """
    Listing quests accepts the supported lifecycle filters. This exercises the `quest
    status filter uses campaign context` scenario and asserts the expected observable
    result or error.
    """
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    SessionStore(path).create(123, "Session 1")
    store = QuestStore(path)
    store.create(123, "Active Quest")
    active = store.create(123, "Second Quest")
    store.complete(123, str(active.id))

    assert len(store.list(123, "all")) == 2
    assert [item.title for item in store.list(123, "active")] == ["Active Quest"]
    assert [item.title for item in store.list(123, "completed")] == ["Second Quest"]
    assert [item.title for item in store.list(123, "finished")] == ["Second Quest"]

    with pytest.raises(QuestNotFoundError):
        store.find("Missing Quest", CampaignStore(path).current(123).id)


def test_quest_progress_records_history_for_current_session_and_quest(
    tmp_path,
) -> None:
    """Quest progress creates immutable history tied to the current campaign/session."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    SessionStore(path).create(123, "Session 1")
    quest = QuestStore(path).create(123, "Rescue the Merchant")

    progress = QuestStore(path).create_progress(
        123,
        str(quest.id),
        "Found tracks leading to the abandoned mine.",
    )

    assert progress.quest_id == quest.id
    assert progress.session_id > 0
    assert progress.description == "Found tracks leading to the abandoned mine."
    assert [
        item.description for item in QuestStore(path).list_progress(123, str(quest.id))
    ] == [progress.description]
    assert [
        item.description
        for item in QuestStore(path).progress_history(123, str(quest.id))
    ] == [progress.description]
    assert [
        item.description
        for item in QuestProgressStore(path).list_by_quest(123, str(quest.id))
    ] == [progress.description]

    QuestStore(path).complete(123, str(quest.id))
    with pytest.raises(ValueError):
        QuestStore(path).create_progress(
            123,
            str(quest.id),
            "This should be rejected.",
        )


def test_quest_progress_requires_valid_campaign_session_and_active_quest(
    tmp_path,
) -> None:
    """Quest progress is rejected without campaign context or for closed quests."""
    path = tmp_path / "journalbot.sqlite3"
    store = QuestProgressStore(path)

    with pytest.raises(Exception):
        store.create(123, "Rescue the Merchant", "progress")

    CampaignStore(path).create(123, "Kingmaker", None)
    with pytest.raises(Exception):
        store.create(123, "Rescue the Merchant", "progress")

    SessionStore(path).create(123, "Session 1")
    quest = QuestStore(path).create(123, "Rescue the Merchant")

    with pytest.raises(QuestNotFoundError):
        store.list_for_quest(123, "Missing Quest")

    with pytest.raises(ValueError):
        store.create(123, str(quest.id), "")

    QuestStore(path).complete(123, str(quest.id))
    with pytest.raises(ValueError):
        store.create(123, str(quest.id), "No longer allowed")


def test_quest_progress_preserves_history_across_sessions_and_keeps_quest_active(
    tmp_path,
) -> None:
    """Progress remains ordered and persistent while Quest status stays unchanged."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    sessions = SessionStore(path)
    first_session = sessions.create(123, "Opening")
    quests = QuestStore(path)
    quest = quests.create(123, "Find the Merchant")

    first = quests.create_progress(123, str(quest.id), "Found the merchant's cart.")
    assert quests.find(str(quest.id), quest.campaign_id).status == "ACTIVE"

    sessions.end_current(123)
    second_session = sessions.create(123, "Investigation")
    second = quests.create_progress(
        123,
        str(quest.id),
        "Discovered who kidnapped the merchant.",
    )

    reopened = QuestStore(path)
    history = reopened.list_progress(123, str(quest.id))

    assert first.session_id == first_session.id
    assert second.session_id == second_session.id
    assert [entry.id for entry in history] == [first.id, second.id]
    assert [entry.description for entry in history] == [
        "Found the merchant's cart.",
        "Discovered who kidnapped the merchant.",
    ]
    assert reopened.find(str(quest.id), quest.campaign_id).status == "ACTIVE"


def test_quest_progress_rejects_a_session_from_another_campaign(tmp_path) -> None:
    """Progress cannot combine a Quest and current Session from different campaigns."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaign_a = campaigns.create(123, "Campaign A", None)
    sessions = SessionStore(path)
    session_a = sessions.create(123, "Session A")
    quests = QuestStore(path)
    quests.create(123, "Quest A")
    sessions.end_current(123)

    campaign_b = campaigns.create(123, "Campaign B", None)
    session_b = sessions.create(123, "Session B")
    quest_b = quests.create(123, "Quest B")

    factory = create_session_factory(path)
    with factory.begin() as db:
        context = db.get(ServerContextModel, "123")
        assert context is not None
        context.current_session_id = session_a.id

    with pytest.raises(
        ValueError,
        match="selected session does not belong to the current campaign",
    ):
        quests.create_progress(123, str(quest_b.id), "Cross-campaign entry")

    assert campaign_a.id != campaign_b.id
    assert session_b.campaign_id == campaign_b.id


def test_database_enforces_quest_progress_foreign_keys(tmp_path) -> None:
    """QuestProgress cannot reference a missing Quest or Session."""
    path = tmp_path / "journalbot.sqlite3"
    CampaignStore(path).create(123, "Kingmaker", None)
    session = SessionStore(path).create(123, "Opening")
    quest = QuestStore(path).create(123, "Find the Merchant")
    factory = create_session_factory(path)

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                QuestProgressModel(
                    quest_id=999,
                    session_id=session.id,
                    description="Invalid quest reference",
                    created_at="now",
                )
            )

    with pytest.raises(IntegrityError):
        with factory.begin() as db:
            db.add(
                QuestProgressModel(
                    quest_id=quest.id,
                    session_id=999,
                    description="Invalid session reference",
                    created_at="now",
                )
            )
