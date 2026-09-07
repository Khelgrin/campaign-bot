# JournalBot

Discord bot MVP for managing Pathfinder 2e campaign journals.

## Run locally

1. Install the project dependencies with `uv sync`.
2. Create a Discord application and bot in the [Discord Developer Portal](https://discord.com/developers/applications), then copy its token.
3. Copy `.env.example` to `.env`, then put the token in `DISCORD_TOKEN`. The
   `.env` file is ignored by Git and must not be committed.
4. Run `uv run journalbot`.

To have the bot announce when it starts, optionally set
`DISCORD_READY_CHANNEL_ID` to a text-channel ID in `.env`. The bot sends `Ready
to rumble` once after a successful connection. Discord Developer Mode must be
enabled to copy a channel ID from the channel's context menu.

Campaign data is stored in SQLite. By default it is kept at
`data/journalbot.sqlite3`; set `JOURNALBOT_DATABASE_PATH` to use another file.
For deployment, point it at a file on persistent storage. The selected campaign
is stored per Discord guild and survives bot restarts.

In the Discord Developer Portal, open the bot's **Bot** settings and enable the
**Message Content Intent** under *Privileged Gateway Intents*. This is required
for the bot to read `Bot: describe` messages.

Alternatively run Makefile commands.

## Quality checks

Run static checks and the offline unit test suite before pushing changes:

```text
make lint
make test
make coverage
make coverage-check
```

`make coverage` prints the overall coverage and writes HTML and XML reports.
`make coverage-check` additionally uses `diff-cover` to verify that changed
lines have at least 80% coverage. Set `BASE_REF` to compare against another Git
ref, for example `make coverage-check BASE_REF=origin/main`.

Local and CI coverage checks use the same Makefile commands. Locally,
`BASE_REF` defaults to `HEAD` and checks staged or unstaged changes. GitHub
Actions compares pull requests with their base commit, or pushes with the
previous commit. CI also uploads the generated HTML and XML reports as the
`coverage-reports` workflow artifact.

The pytest suite uses mocked Discord objects, so it does not require a bot token,
a running bot, or access to a Discord server. GitHub Actions runs both checks on
pushes and pull requests.

The bot also accepts `DISCORD_TOKEN` as a regular environment variable. This is
the intended deployment configuration: set the secret in the chosen host's secret
manager or environment-variable settings, rather than uploading a `.env` file.
Hosting and deployment infrastructure remain intentionally undecided.

The bot connects to Discord, logs when it is ready, and supports campaign,
session, and quest commands such as `!start-campaign`, `!use-campaign`,
`!list-campaign`, `!read-campaign`, `!update-campaign`, `!end-campaign`,
`!start-session`, `!use-session`, `!list-session`, `!read-session`,
`!update-session`, `!end-session`, `!create-quest`, `!update-quest`,
`!quest-details`, `!list-quests`, `!complete-quest`, `!fail-quest`, and
`!journal` for the interactive journal panel.
Send `Bot: help` or `Bot: commands` to list them.
