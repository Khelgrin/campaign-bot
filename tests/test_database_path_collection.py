# tests/test_database.py

from pathlib import Path
from unittest.mock import patch

import pytest

from journalbot.database import DEFAULT_DATABASE_PATH, get_database_path


@pytest.mark.parametrize(
    ("database_url", "configured_path", "expected"),
    [
        (
            "postgres://user:pass@localhost:5432/journal",
            None,
            "postgresql://user:pass@localhost:5432/journal",
        ),
        (
            "postgresql://user:pass@localhost:5432/journal",
            None,
            "postgresql://user:pass@localhost:5432/journal",
        ),
    ],
)
def test_get_database_path_returns_deployed_database_url(
    database_url: str,
    configured_path: str | None,
    expected: str,
) -> None:
    with patch.dict(
        "os.environ",
        {
            "DATABASE_URL": database_url,
            **(
                {"JOURNALBOT_DATABASE_PATH": configured_path}
                if configured_path
                else {}
            ),
        },
        clear=True,
    ):
        result = get_database_path()

    assert result == expected


def test_get_database_path_returns_configured_local_path() -> None:
    configured_path = "/tmp/journalbot.db"

    with patch.dict(
        "os.environ",
        {"JOURNALBOT_DATABASE_PATH": configured_path},
        clear=True,
    ):
        result = get_database_path()

    assert result == Path(configured_path)
    assert isinstance(result, Path)


def test_get_database_path_returns_default_when_nothing_is_configured() -> None:
    with patch.dict("os.environ", {}, clear=True):
        result = get_database_path()

    assert result == DEFAULT_DATABASE_PATH


def test_database_url_takes_precedence_over_configured_local_path() -> None:
    database_url = "postgres://user:pass@localhost:5432/journal"
    configured_path = "/tmp/journalbot.db"

    with patch.dict(
        "os.environ",
        {
            "DATABASE_URL": database_url,
            "JOURNALBOT_DATABASE_PATH": configured_path,
        },
        clear=True,
    ):
        result = get_database_path()

    assert result == "postgresql://user:pass@localhost:5432/journal"