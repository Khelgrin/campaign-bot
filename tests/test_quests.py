"""Tests for quest persistence and lifecycle."""

import pytest
from sqlalchemy.exc import IntegrityError

from journalbot.campaigns import CampaignStore
from journalbot.database import QuestModel, create_session_factory
from journalbot.quests import (
    AmbiguousQuestError,
    QuestNotFoundError,
    QuestStore,
)
from journalbot.sessions import SessionStore


def test_quest_creation_requires_active_campaign_and_session(tmp_path) -> None:
    """Creating a quest requires both campaign and session context."""
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


def test_quest_update_and_completion_keep_identity_and_history(tmp_path) -> None:
    """Quest metadata changes preserve identity while lifecycle changes are explicit."""
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
    """The same quest title can recur across campaigns but not within one campaign."""
    path = tmp_path / "journalbot.sqlite3"
    campaigns = CampaignStore(path)
    campaigns.create(123, "Campaign A", None)
    SessionStore(path).create(123, "Session 1")
    first = QuestStore(path).create(123, "Escort the Merchant")

    campaigns.create(123, "Campaign B", None)
    SessionStore(path).create(123, "Session 1")
    second = QuestStore(path).create(123, "Escort the Merchant")

    assert (
        QuestStore(path).find(str(first.id), campaigns.find("Campaign A").id)
        == first
    )
    assert (
        QuestStore(path).find(str(second.id), campaigns.find("Campaign B").id)
        == second
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
    """Quest lifecycle fields must match the accepted state machine."""
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
    """Listing quests accepts the supported lifecycle filters."""
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
