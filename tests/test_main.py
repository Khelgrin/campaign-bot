"""Unit tests for the JournalBot application entry point."""

from unittest.mock import MagicMock

import pytest

from journalbot import main as application


def test_main_requires_a_discord_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup fails clearly when no token is configured."""
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setattr(application, "load_dotenv", MagicMock())

    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        application.main()


def test_main_runs_created_bot_with_configured_token(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup passes the configured token to the Discord client."""
    bot = MagicMock()
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setattr(application, "load_dotenv", MagicMock())
    monkeypatch.setattr(application, "create_bot", MagicMock(return_value=bot))

    application.main()

    bot.run.assert_called_once_with("test-token", log_handler=None)
