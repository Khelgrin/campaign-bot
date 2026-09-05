# JournalBot

Discord bot MVP for managing Pathfinder 2e campaign journals.

## Run locally

1. Install the project dependencies with `uv sync`.
2. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications), then copy its token.
3. Copy `.env.example` to `.env`, then put the token in `DISCORD_TOKEN`. The
   `.env` file is ignored by Git and must not be committed.
4. Run `uv run journalbot`.

Alternatively run Makefile commands.

The bot also accepts `DISCORD_TOKEN` as a regular environment variable. This is
the intended deployment configuration: set the secret in the chosen host's secret
manager or environment-variable settings, rather than uploading a `.env` file.
Hosting and deployment infrastructure remain intentionally undecided.

The current skeleton connects to Discord and logs when it is ready. It deliberately
contains no campaign or journal commands yet.
