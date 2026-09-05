"""Tests for persistent campaigns and guild campaign context."""

import pytest
from sqlalchemy.exc import IntegrityError

from journalbot.campaigns import CampaignStore, NoCampaignSelectedError
from journalbot.database import CampaignModel, create_session_factory


def test_campaign_context_survives_a_new_store_instance(tmp_path) -> None:
    """The selected campaign is read back from the database after a restart."""
    database_path = tmp_path / "journalbot.sqlite3"
    campaign = CampaignStore(database_path).create(123, "Kingmaker", "Stolen land")

    restored = CampaignStore(database_path).current(123)

    assert restored == campaign


def test_starting_a_campaign_replaces_only_the_guild_context(tmp_path) -> None:
    """Guilds have independent contexts and creating does not end old campaigns."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")
    first = store.create(123, "First", None)
    second = store.create(123, "Second", None)
    other = store.create(456, "Other", None)

    assert store.current(123).id == second.id
    assert store.current(456).id == other.id
    assert store.find(str(first.id)).status == "ACTIVE"


def test_missing_context_is_explicit(tmp_path) -> None:
    """A guild without a selection cannot resolve a current campaign."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")

    with pytest.raises(
        NoCampaignSelectedError, match="No campaign is currently selected"
    ):
        store.current(123)


def test_ending_preserves_data_and_sets_end_timestamp(tmp_path) -> None:
    """Ending a campaign changes lifecycle state without deleting it."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")
    campaign = store.create(123, "Finished", None)

    ended = store.end_current(123)

    assert ended.id == campaign.id
    assert ended.status == "ENDED"
    assert ended.ended_at is not None
    assert store.find(str(campaign.id)).title == "Finished"


def test_database_enforces_campaign_lifecycle_invariants(tmp_path) -> None:
    """The schema rejects inconsistent status and ended_at values."""
    database_path = tmp_path / "journalbot.sqlite3"
    session_factory = create_session_factory(database_path)
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                CampaignModel(
                    title="Invalid",
                    description=None,
                    status="ACTIVE",
                    created_at="now",
                    ended_at="should be null",
                )
            )
