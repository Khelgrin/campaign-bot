"""Application entry point for JournalBot."""

import logging
import os

from dotenv import load_dotenv

from journalbot.bot import create_bot


def configure_logging() -> None:
    """Configure application logging for command-line execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    """Start the bot using a system environment variable or local .env file."""
    configure_logging()
    load_dotenv()
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        message = "DISCORD_TOKEN must be set in the environment or a local .env file."
        raise RuntimeError(message)

    create_bot().run(token, log_handler=None)


if __name__ == "__main__":
    main()
