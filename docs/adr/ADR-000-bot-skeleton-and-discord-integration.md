# ADR-000: Bot Skeleton and Discord Integration Baseline

**Status:** Recorded
**Scope:** Bootstrap

## Context

JournalBot began as an empty Python project. Before the manual-journal MVP can
be implemented, it needs a repeatable way to start a Discord bot locally and
connect that bot to a Discord guild.

This document records the working baseline. It is not a decision about campaign
data, persistence, deployment hosting, or the final command interface.

## Implemented Baseline

The application is a Python package run with `uv`.

```text
src/journalbot/
    main.py       application entry point
    bot.py        Discord bot and event handlers
```

`JournalBot` subclasses `discord.ext.commands.Bot`. Its `on_ready` event logs
the authenticated bot identity and the guilds visible to it. Its `on_message`
event currently supports small bootstrap text commands:

| Message | Purpose |
| --- | --- |
| `Bot: describe` | Describes the bot's purpose. |
| `Bot: help` / `Bot: commands` | Lists the currently available text commands. |

These text triggers are temporary bootstrap behavior. They do not establish the
future MVP command architecture.

## Local Configuration

`DISCORD_TOKEN` authenticates the bot. Locally it is loaded from an ignored
`.env` file using `python-dotenv`; `.env.example` documents the required values.

```text
DISCORD_TOKEN=<bot token>
DISCORD_READY_CHANNEL_ID=<optional text channel ID>
```

`.env` must never be committed. For a future deployment, the same variables are
expected to come from the host's environment or secret manager rather than from
an uploaded `.env` file.

The application can be started with:

```text
make run
```

The optional `DISCORD_READY_CHANNEL_ID` causes the bot to send `Ready to rumble`
once after a successful connection.

## Discord Guild Integration

The Discord application must have a bot user and be installed to the target
server with the `bot` OAuth2 scope. An application merely listed under a server's
Integrations settings is not sufficient: the bot user must be a member of the
guild.

The bot needs the following permissions in every channel it uses:

```text
View Channel
Send Messages
```

Channel and category permission overrides can deny access even when the bot role
has server-level permissions. A `403 Missing Access` response when fetching a
channel indicates that the bot cannot see that specific channel.

Reading normal message text also requires both of the following:

1. `intents.message_content = True` in application code.
2. **Message Content Intent** enabled for the application in the Discord
   Developer Portal.

## Verification

```text
make lint
make test
make run
```

`make lint` runs Ruff and mypy. `make test` runs the offline pytest suite, which
uses mocked Discord objects and does not require a bot token, a running bot, or
Discord network access. The tests cover current startup configuration, intent
setup, text-command responses, ready-announcement behavior, and invalid
configuration handling.

GitHub Actions runs linting and unit tests on pushes and pull requests. On
startup, the bot log identifies the running bot and the guilds it can access.
The bot is ready for subsequent manual-journal work once it is visible to the
target guild and can send messages in the configured channel.

## Out of Scope

This baseline intentionally does not decide or implement:

* deployment hosting or release automation,
* database or domain models,
* campaign/session/quest features,
* recording, transcription, AI, Roll20 integration, or permissions.

ADR-001 remains the first accepted architectural decision and governs persistent
campaign context.
