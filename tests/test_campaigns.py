"""Tests for persistent campaigns and guild campaign context."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from journalbot.campaigns import (
    AmbiguousCampaignError,
    CampaignNotFoundError,
    CampaignStore,
    NoCampaignSelectedError,
)
from journalbot.database import (
    CampaignModel,
    ServerContextModel,
    create_session_factory,
)


def test_create_initializes_an_active_campaign(tmp_path) -> None:
    """Creating a campaign sets its required initial lifecycle fields."""
    campaign = CampaignStore(tmp_path / "journalbot.sqlite3").create(
        123, "Kingmaker", "Stolen land"
    )

    assert campaign.id > 0
    assert campaign.title == "Kingmaker"
    assert campaign.description == "Stolen land"
    assert campaign.status == "ACTIVE"
    assert campaign.created_at
    assert campaign.ended_at is None


def test_find_reads_campaigns_by_id_or_exact_title(tmp_path) -> None:
    """Campaigns can be read using either supported identifier form."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")
    campaign = store.create(123, "Kingmaker", None)

    assert store.find(str(campaign.id)) == campaign
    assert store.find("Kingmaker") == campaign


def test_find_rejects_missing_and_ambiguous_campaigns(tmp_path) -> None:
    """Invalid identifiers produce explicit errors rather than guesses."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")
    store.create(123, "Duplicate", None)
    store.create(456, "Duplicate", None)

    with pytest.raises(AmbiguousCampaignError):
        store.find("Duplicate")
    with pytest.raises(CampaignNotFoundError):
        store.find("missing")


def test_update_changes_metadata_without_changing_id(tmp_path) -> None:
    """Updating metadata preserves the campaign's stable identifier."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")
    campaign = store.create(123, "Original", "Old description")

    updated = store.update(str(campaign.id), "Renamed", "New description")

    assert updated.id == campaign.id
    assert updated.title == "Renamed"
    assert updated.description == "New description"
    assert updated.status == "ACTIVE"
    assert updated.ended_at is None


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


def test_guild_has_one_persisted_context_row(tmp_path) -> None:
    """Repeated selections update one guild context instead of creating rows."""
    database_path = tmp_path / "journalbot.sqlite3"
    store = CampaignStore(database_path)
    first = store.create(123, "First", None)
    second = store.create(123, "Second", None)

    assert store.select(123, str(first.id)).id == first.id
    assert store.current(123).id == first.id

    with store.session_factory() as session:
        contexts = session.scalars(
            select(ServerContextModel).where(
                ServerContextModel.discord_guild_id == "123"
            )
        ).all()

    assert len(contexts) == 1
    assert contexts[0].current_campaign_id == first.id
    assert second.id != first.id


def test_select_persists_for_a_new_store_instance(tmp_path) -> None:
    """Selecting a campaign remains effective after reopening the database."""
    database_path = tmp_path / "journalbot.sqlite3"
    store = CampaignStore(database_path)
    first = store.create(123, "First", None)
    second = store.create(123, "Second", None)

    store.select(123, str(first.id))

    assert CampaignStore(database_path).current(123).id == first.id
    assert second.id != first.id


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


def test_ended_campaign_can_still_be_selected_and_read(tmp_path) -> None:
    """Ending a campaign does not prevent later selection or reading."""
    store = CampaignStore(tmp_path / "journalbot.sqlite3")
    campaign = store.create(123, "Finished", None)
    store.end_current(123)

    selected = store.select(456, str(campaign.id))

    assert selected.status == "ENDED"
    assert store.current(456).id == campaign.id
    assert store.find(str(campaign.id)).ended_at is not None


@pytest.mark.parametrize(
    ("status", "ended_at"),
    [("ACTIVE", "should be null"), ("ENDED", None), ("OTHER", None)],
)
def test_database_enforces_campaign_lifecycle_invariants(
    tmp_path, status: str, ended_at: str | None
) -> None:
    """The schema rejects inconsistent status and ended_at values."""
    database_path = tmp_path / "journalbot.sqlite3"
    session_factory = create_session_factory(database_path)
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                CampaignModel(
                    title="Invalid",
                    description=None,
                    status=status,
                    created_at="now",
                    ended_at=ended_at,
                )
            )
