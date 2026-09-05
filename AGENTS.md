# RPG Journal Bot — Agent Context

## Project Overview

This project is a Discord bot for maintaining a structured journal of Pathfinder 2e RPG campaigns.

The group plays using:

* Discord for voice communication, chat and occasional images.
* Roll20 for gameplay, maps and dice.

The project will eventually support:

1. Manual campaign/session/journal management.
2. Discord voice recording.
3. Audio transcription.
4. AI-assisted session journal generation.
5. Potential integration with Discord images and Roll20 data.

**Current scope is strictly the manual journal bot.**

Do not implement recording, transcription, AI summarization, Roll20 integration or permissions unless explicitly requested.

No implementation decisions should be made based on assumptions about future AI functionality.

---

# Product Development Approach

Development should proceed incrementally.

Current roadmap:

```text
Phase 1 — Manual Journal
    Campaign
    Session
    Quest
    Journal / events

Phase 2 — Discord Recording

Phase 3 — Transcription

Phase 4 — AI-generated Session Journal

Phase 5 — Possible Roll20 / Discord integrations
```

The current task is Phase 1.

The data model should be designed so that later phases can build on it, but future functionality should not unnecessarily complicate the MVP.

Prefer simple, explicit implementations over speculative abstractions.

---

# Current Domain Hierarchy

The journal is organized around a campaign:

```text
Discord Guild
    │
    └── ServerContext
            │
            └── current_campaign_id
                    │
                    ▼
                 Campaign
                    │
                    ├── Session[]
                    │
                    ├── Quest[]
                    │
                    └── future journal objects
```

`Campaign` is currently the highest-level domain object.

All child objects must have an explicit relationship to a campaign.

For example:

```text
Quest.campaign_id
Session.campaign_id
```

---

# Campaign

A Campaign represents a single RPG campaign.

## Campaign fields

```text
id
title
description
status
created_at
ended_at
```

### Field semantics

* `id` — immutable unique identifier.
* `title` — campaign name.
* `description` — optional campaign description/context.
* `status` — `ACTIVE` or `ENDED`.
* `created_at` — creation timestamp.
* `ended_at` — timestamp when the campaign was ended; `NULL` while active.

Integrity rules:

```text
ACTIVE → ended_at IS NULL
ENDED  → ended_at IS NOT NULL
```

Campaign IDs must remain stable even if the campaign title changes.

---

# Campaign Commands

The MVP Campaign interface consists of:

```text
/start-campaign <title> <description>
/use-campaign <id/title>
/list-campaign
/read-campaign <id/title>
/update-campaign <id/title> [title] [description]
/end-campaign
```

## `/start-campaign`

Creates a new Campaign.

The newly created campaign becomes the current campaign for the Discord guild.

Creating a new campaign does NOT automatically end an existing campaign.

## `/use-campaign`

Selects a campaign as the current campaign context for the Discord guild.

The campaign may be identified by ID or title.

## `/list-campaign`

Lists available campaigns with at least:

```text
ID
Title
Status
```

The currently selected campaign should ideally be visually identifiable.

## `/read-campaign`

Displays campaign details.

At minimum:

```text
ID
Title
Description
Status
Created at
Ended at
```

Future versions may add aggregate information such as session and quest counts.

## `/update-campaign`

Updates campaign metadata.

Supported fields:

```text
title
description
```

Updating a campaign must not change its ID.

## `/end-campaign`

Ends the currently selected campaign.

Effect:

```text
status = ENDED
ended_at = current timestamp
```

Ending a campaign does not delete its data.

---

# Campaign Context

The currently selected campaign is persistent state associated with a Discord guild.

It must NOT be stored only in application memory.

Use a `ServerContext` concept/table.

## ServerContext

```text
discord_guild_id
current_campaign_id
updated_at
```

Relationship:

```text
ServerContext.current_campaign_id → Campaign.id
```

`current_campaign_id` may be `NULL`.

The context is scoped to the Discord guild.

For MVP:

> All users on the same Discord guild share the same current campaign.

Do not implement user-specific or channel-specific campaign contexts.

---

# Context Resolution

Commands operating on child objects should resolve their campaign from the current guild context.

Example:

```text
/use-campaign 42

/new-quest "Find the Witch" "Investigate the strange events..."
```

The second command must result in:

```text
Quest.campaign_id = 42
```

The user should not have to specify `campaign_id` for every child-object command.

The expected resolution flow is:

```text
Discord guild ID
    ↓
ServerContext
    ↓
current_campaign_id
    ↓
Campaign
    ↓
create/update child object
```

---

# Missing Campaign Context

If:

```text
ServerContext.current_campaign_id = NULL
```

a command requiring a campaign context must fail clearly.

Example:

```text
No campaign is currently selected.
Use /use-campaign <id> first.
```

The bot must never guess which campaign the user intended.

---

# Ended Campaigns

An ended campaign remains in the database.

It can still be:

* listed,
* read,
* selected as the current campaign.

The MVP does not require:

```text
/delete-campaign
/reopen-campaign
```

Do not implement these unless explicitly requested.

---

# Permissions

Permissions and roles are intentionally out of scope for MVP.

Assume that the project will initially be managed by one trusted user.

Do not introduce:

* role systems,
* user permissions,
* ownership models,
* access control,
* campaign sharing rules.

These will be addressed after the MVP.

---

# Important Product Principles

## Keep the MVP small

Do not prematurely implement features for:

* recording,
* transcription,
* AI,
* Roll20,
* automatic event extraction,
* complex permissions,
* multi-campaign concurrency.

## Preserve structured history

Journal data should generally preserve historical information rather than only storing the latest state.

For example, quest progress should eventually be represented as individual progress entries/events rather than repeatedly overwriting one text field.

This is important for future session summaries and AI-generated journals.

## Separate current state from history

A domain object may have a current state while historical changes/events are retained separately.

Example:

```text
Quest
    current status
    current title
    current description
    │
    └── QuestProgress[]
```

Do not destroy historical journal information simply because the current state changes.

---

# Current Product Priority

Implement in this order:

```text
1. Campaign
2. Session
3. Quest
4. Quest progress/history
5. Journal/session event model
6. Read/query commands
```

Only after the manual journal is usable should recording/transcription be considered.

---

# Architecture Decision Records

Detailed architectural decisions are stored under:

```text
docs/adr/
```

The first accepted ADR is:

```text
docs/adr/ADR-001-campaign-context.md
```

ADR-001 defines the persistent Discord-guild campaign context and should be treated as the authoritative decision for that topic.

When making a decision that contradicts an existing ADR, do not silently override it. Update the ADR or explicitly flag the conflict.

---

# Working Rules for Codex

1. Do not write code outside the currently requested scope.
2. Before introducing a new domain object, clarify its relationship to Campaign.
3. Prefer simple database models suitable for an MVP.
4. Keep IDs stable and use foreign-key relationships between domain objects.
5. Keep Discord-specific context separate from domain objects where practical.
6. Do not use in-memory state as the source of truth for persistent application state.
7. Do not implement permissions yet.
8. Do not implement recording/transcription/AI/Roll20 functionality yet.
9. Preserve historical journal information where it has future analytical value.
10. When a requirement is ambiguous, identify the ambiguity before making a significant architectural decision.
11. Treat ADRs as project-level architectural decisions.
12. Avoid speculative abstractions that exist only for possible future features.

---

# Current Status

The following decisions are already accepted:

```text
Campaign:
    ✓ Defined
    ✓ Database schema defined
    ✓ Lifecycle defined
    ✓ Commands defined
    ✓ Persistent guild-level context defined

Session:
    ☐ Not yet designed

Quest:
    ☐ Not yet designed

Journal events:
    ☐ Not yet designed

Recording:
    ☐ Future

Transcription:
    ☐ Future

AI journal generation:
    ☐ Future

Permissions:
    ☐ Post-MVP
```

The next design task is to define the `Session` domain object and its relationship to `Campaign`.
