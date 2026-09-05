# ADR-001: Campaign Context Management

**Status:** Accepted
**Scope:** MVP
**Related Object:** `Campaign`

## 1. Context

The RPG journal bot organizes all journal data under a `Campaign`.

Commands operating on child objects such as `Session` and `Quest` should not require the user to specify a `campaign_id` on every command.

Instead, the bot maintains a **current campaign context per Discord server (guild)**.

## 2. Decision

The currently selected campaign will be stored persistently in the database as part of a `ServerContext` object.

The context is scoped to a **Discord guild**.

### `Campaign` table

```text
Campaign
────────────────────────────────────────
id              UUID / integer    PK
title           VARCHAR / TEXT    NOT NULL
description     TEXT              NULL
status          ENUM              NOT NULL
created_at      DATETIME          NOT NULL
ended_at        DATETIME          NULL
```

### Field definitions

| Field         | Type           | Constraints | Description                                 |
| ------------- | -------------- | ----------- | ------------------------------------------- |
| `id`          | UUID / integer | Primary key | Unique campaign identifier                  |
| `title`       | string         | NOT NULL    | Campaign title                              |
| `description` | text           | NULL        | Campaign description and context            |
| `status`      | enum           | NOT NULL    | `ACTIVE` or `ENDED`                         |
| `created_at`  | datetime       | NOT NULL    | Campaign creation timestamp                 |
| `ended_at`    | datetime       | NULL        | Campaign end timestamp; `NULL` while active |

### Campaign status

```text
ACTIVE
ENDED
```

Data integrity rules:

```text
ACTIVE → ended_at IS NULL
ENDED  → ended_at IS NOT NULL
```

The campaign `id` is immutable. Updating the title must never change the ID.

---

### `ServerContext` table

```text
ServerContext
────────────────────────────────────────
discord_guild_id       VARCHAR / BIGINT    PK
current_campaign_id    UUID / integer      FK → Campaign.id, NULL
updated_at              DATETIME            NOT NULL
```

Relationship:

```text
Discord Guild
      │
      │ 1:1
      ▼
ServerContext
      │
      │ current_campaign_id
      ▼
Campaign
```

`ServerContext` stores only the currently selected campaign reference. It does not duplicate campaign data.

## 3. Campaign Lifecycle

### Creating a campaign

```text
!start-campaign title="..." [description="..."]
```

Creates:

```text
Campaign.status = ACTIVE
Campaign.created_at = now()
Campaign.ended_at = NULL
```

The newly created campaign becomes the current campaign for the Discord guild.

An existing campaign is **not automatically ended**.

### Selecting a campaign

```text
!use-campaign <identifier>
```

Updates:

```text
ServerContext.current_campaign_id = selected_campaign.id
ServerContext.updated_at = now()
```

### Ending a campaign

```text
!end-campaign
```

Updates:

```text
Campaign.status = ENDED
Campaign.ended_at = now()
```

The campaign remains in the database and can still be read.

## 4. Campaign Commands

| Command                                             | Description                                          |
| --------------------------------------------------- | ---------------------------------------------------- |
| `!start-campaign title="..." [description="..."]`   | Creates a campaign and makes it the current campaign |
| `!use-campaign <identifier>`                       | Selects the campaign as the current guild context    |
| `!list-campaign`                                    | Lists all campaigns with ID, title and status        |
| `!read-campaign <identifier>`                      | Displays campaign details                            |
| `!update-campaign <identifier> [title="..."] [description="..."]` | Updates campaign metadata |
| `!end-campaign`                                     | Marks the current campaign as `ENDED`                |

The MVP does not include:

```text
!delete-campaign
!reopen-campaign
```

## 5. Context Resolution

Commands operating on child objects resolve their campaign through `ServerContext`.

Example:

```text
!new-quest "Find the Witch" "Investigate the strange events..."
```

Resolution:

```text
Discord guild ID
      ↓
ServerContext
      ↓
current_campaign_id
      ↓
Campaign
      ↓
create Quest(campaign_id = current_campaign_id)
```

The user does not need to provide the campaign ID explicitly.

## 6. No Campaign Selected

If:

```text
ServerContext.current_campaign_id = NULL
```

a command requiring campaign context must fail.

Example response:

```text
No campaign is currently selected.
Use !use-campaign <id> first.
```

The bot must not guess or implicitly select a campaign.

## 7. Persistence

The current campaign must be persisted in the database.

In-memory state must not be the source of truth.

After a bot restart, deployment, or crash, the selected campaign must remain available.

## 8. Scope

The current campaign is scoped to the **Discord guild**.

All users on the same guild share the same current campaign.

The MVP does not implement:

* user-specific campaign contexts,
* channel-specific campaign contexts,
* permissions,
* roles,
* campaign access control.

## 9. Future Extensions

`ServerContext` should remain extensible.

Potential future fields:

```text
current_session_id
journal_channel_id
default_timezone
journal_settings
```

Potential future support for multiple simultaneous campaign contexts can be added without changing the fundamental `Campaign` model.

## 10. MVP Acceptance Criteria

* [x] `Campaign` can be created, read, updated and ended.
* [x] Every campaign has a stable unique ID.
* [x] Campaign status is either `ACTIVE` or `ENDED`.
* [x] `ACTIVE` campaigns have `ended_at = NULL`.
* [x] `ENDED` campaigns have a non-null `ended_at`.
* [x] A Discord guild can have zero or one current campaign.
* [x] `!use-campaign` changes the persistent current campaign unless the
  currently selected campaign has an active session.
* [x] `!start-campaign` automatically selects the newly created campaign.
* [x] Campaign context survives bot restart.
* [ ] Child-object commands automatically use the current campaign.
* [x] Commands requiring campaign context fail when no campaign is selected.
* [x] Ending a campaign does not delete its data.
* [x] All users on the guild share the same campaign context.
* [x] Permissions are out of scope for MVP.
