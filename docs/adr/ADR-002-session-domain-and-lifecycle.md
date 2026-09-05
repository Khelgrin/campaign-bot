# ADR-002: Session Domain and Lifecycle

**Status:** Proposed
**Scope:** MVP
**Related Objects:** `Campaign`, `ServerContext`

## 1. Context

A `Campaign` is made up of individual play sessions. A session is the manual
record of one RPG meeting and is the parent for future journal entries,
transcripts, and other session-specific information.

The Session design must support the current manual-journal MVP without
introducing recording, transcription, AI, Roll20 integration, or permissions.
It must also preserve stable relationships so later journal features can attach
data to a specific campaign and session.

ADR-001 defines the persistent guild-level campaign context. Session commands
must use that campaign context rather than accepting an arbitrary
`campaign_id`.

## 2. Decision Proposal

Introduce `Session` as a child of `Campaign`.

```text
Campaign
    │
    └── Session[]
```

Every session has a non-null `campaign_id`. A session ID is immutable and is
the preferred identifier for future references.

The MVP represents a session with a small lifecycle:

```text
ACTIVE → ENDED
```

Creating a session makes it active. Ending a session records its end timestamp
but does not delete or archive its data.

The design intentionally does not model planned sessions, recurring events,
players, attendance, locations, or game-system-specific metadata yet.

There must never be more than one active session within a campaign. The bot
supports one weekly table with one GM and five player characters; parallel
sessions are not a supported use case.

## 3. Session Schema

```text
Session
────────────────────────────────────────
id                  INTEGER       PK
campaign_id         INTEGER       FK → Campaign.id, NOT NULL
number              INTEGER       NOT NULL
title               TEXT          NOT NULL
description         TEXT          NULL
status              TEXT          NOT NULL
created_at          DATETIME      NOT NULL
played_at           DATETIME      NOT NULL
ended_at            DATETIME      NULL
```

### Field definitions

| Field | Constraints | Description |
| --- | --- | --- |
| `id` | Primary key, immutable | Stable session identifier |
| `campaign_id` | Required foreign key | Campaign containing the session |
| `number` | Positive; unique within a campaign | Human-friendly sequential number |
| `title` | Required after creation | User-provided label, or generated as `Session <number>` |
| `description` | Optional | Free-form description of what happened during the session |
| `status` | `ACTIVE` or `ENDED` | Current session lifecycle state |
| `created_at` | Required | When the record was created |
| `played_at` | Required, editable | Date/time of the RPG session; defaults to `created_at` |
| `ended_at` | Required only when ended | When the session was closed |

The database must enforce:

```text
ACTIVE → ended_at IS NULL
ENDED  → ended_at IS NOT NULL
UNIQUE (campaign_id, number)
UNIQUE (campaign_id, title)
At most one ACTIVE session per campaign
```

`number` is assigned as the next number within the campaign when the session
is created. It is not used as the foreign-key identity or lookup key; `id`
remains stable if the display numbering policy changes later.

The command does not require a title. When no title is supplied, the bot
persists `Session <number>` as the title. The title may be changed later.
`played_at` defaults to the session creation timestamp and may be corrected
later when the journal is entered after the actual game. Titles must be unique
within a campaign.

## 4. Session Context

The guild context should be extended with an optional current session:

```text
ServerContext
────────────────────────────────────────
discord_guild_id       TEXT          PK
current_campaign_id    INTEGER       FK → Campaign.id, NULL
current_session_id     INTEGER       FK → Session.id, NULL
updated_at             DATETIME      NOT NULL
```

The current session must belong to the current campaign. Selecting a session
also establishes its campaign as the current campaign, so a command cannot
accidentally operate on a session from another campaign.

This extends ADR-001's `ServerContext`; ADR-001's campaign selection remains
the source of truth for campaign context.

Session context is persistent and guild-scoped. All users on a guild share it.
It must survive bot restarts and must not be stored only in application memory.

## 5. Context Resolution

Session commands resolve the campaign in this order:

```text
Discord guild ID
      ↓
ServerContext.current_campaign_id
      ↓
Campaign
      ↓
create or select Session
```

Commands that operate on the current session resolve one additional level:

```text
Discord guild ID
      ↓
ServerContext.current_session_id
      ↓
Session
```

If no campaign is selected, the command must fail clearly:

```text
No campaign is currently selected.
Use !use-campaign <id or title> first.
```

If no session is selected, a session-dependent command must fail clearly:

```text
No session is currently selected.
Use !use-session <id or title> first.
```

The bot must never guess a campaign or session.

## 6. Campaign Lifecycle Interaction

Sessions can be read and listed when their campaign is active or ended.

Creating a new session requires an active campaign. If the selected campaign
is ended, the command must fail without creating a session:

```text
The selected campaign has ended. Select an active campaign first.
```

Ending a campaign is rejected while it has an active session. The active
session must be ended explicitly first; campaign ending must not silently
change session lifecycle data.

An ended session remains readable and selectable. It cannot be edited in ways
that change its lifecycle history; metadata updates remain allowed unless a
later ADR introduces stricter journal immutability.

## 7. Commands

The proposed MVP command interface is:

| Command | Description |
| --- | --- |
| `!start-session [title] [description]` | Create an active session under the current campaign and select it |
| `!use-session <id or title>` | Select a session and make its campaign current |
| `!list-session` | List sessions for the current campaign with number, ID, title, and status |
| `!read-session <id or title>` | Display complete session details |
| `!update-session <id or title> [title] [description] [played_at]` | Update session metadata without changing its ID or number |
| `!end-session` | End the current session and retain its data |

The command names follow the existing text-command implementation. If the
project later migrates to Discord slash commands, the domain operations and
semantics should remain unchanged.

### Command behavior

`!start-session`:

1. Resolve the current guild campaign.
2. Reject the operation if no campaign is selected or the campaign is ended.
3. Reject the operation if the campaign already has an active session.
4. Allocate the next session number for that campaign.
5. Use the supplied title, or generate `Session <number>`.
6. Set `played_at` to the creation timestamp.
7. Create an `ACTIVE` session.
8. Select it in `ServerContext`.

Creating a session never automatically ends another active session. The
operation is rejected instead, and the existing session must be ended first.

`!use-session`, `!read-session`, and `!update-session` accept the stable
session ID or the exact title. Title lookup is scoped to the current campaign.
Because titles are unique within a campaign, title lookup cannot be ambiguous.
Changing a title to one already used by another session in the same campaign
must be rejected.

`!list-session` and `!read-session` may inspect ended sessions. Listing without
a current campaign is an error rather than a global search.

`!end-session` requires a selected session. Repeating the command for an
already ended session is idempotent and returns its existing ended state.

`!end-campaign` must reject the operation when the selected campaign has an
active session:

```text
The campaign has an active session. End the session before ending the campaign.
```

## 8. Domain Operations

The persistence layer should expose explicit operations equivalent to:

```text
create(guild_id, title, description) -> Session
list_current_campaign(guild_id) -> list[Session]
find(identifier, campaign_id) -> Session
select(guild_id, identifier) -> Session
current(guild_id) -> Session
update(identifier, title, description, played_at) -> Session
end_current(guild_id) -> Session
```

The implementation should use the existing `CampaignStore` patterns:

* explicit domain errors for missing and ambiguous context,
* atomic creation plus context selection,
* database-enforced foreign keys and lifecycle constraints,
* UTC timestamps,
* no silent fallback to another campaign or session.

## 9. Out of Scope

This ADR does not implement or decide:

* audio recording or transcription,
* AI-generated summaries,
* Roll20 or Discord message ingestion,
* player or character attendance,
* initiative/combat tracking,
* quests or quest progress,
* journal event types,
* file or media attachments,
* permissions or role-based access,
* deleting or reopening sessions,
* multiple independent session contexts per channel or user.

Session notes in this ADR are metadata only. Structured journal events should
be designed separately and linked to `session_id`.

## 10. Acceptance Criteria

* [ ] A session belongs to exactly one campaign through a required foreign key.
* [ ] Session IDs remain stable when metadata changes.
* [ ] Session numbers are positive and unique within a campaign.
* [ ] Session titles are non-empty and unique within a campaign.
* [ ] Session lifecycle is enforced as `ACTIVE` or `ENDED`.
* [ ] Active sessions have no `ended_at`; ended sessions have an `ended_at`.
* [ ] A campaign cannot have more than one active session.
* [ ] A campaign cannot be ended while it has an active session.
* [ ] A session cannot be created without a selected campaign.
* [ ] A session cannot be created under an ended campaign.
* [ ] Creating a session selects it persistently for the guild.
* [ ] Session selection persists after a bot restart.
* [ ] Selecting a session also selects its campaign.
* [ ] Session listing and reading are scoped to the current campaign.
* [ ] Ending a session preserves its record and historical timestamps.
* [ ] `played_at` defaults to creation time and can be corrected later.
* [ ] Missing campaign and session context produce explicit user-facing errors.
* [ ] No permissions or future-phase integrations are introduced.

## 11. Product Decisions Recorded

* Ending a campaign is rejected while it has an active session.
* Starting a session is rejected when the campaign already has an active
  session.
