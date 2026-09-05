# ADR-004: QuestProgress Domain and Lifecycle

**Status:** Accepted
**Date:** 2026-09-05

## 1. Context

Players need to be able to see not only the current status of a Quest, but also the path the party took while solving it.

For example:

```text
Quest: Find the Missing Merchant

Session 3
Mayor asked us to find the missing merchant.

Session 4
We found the merchant's cart.

Session 5
We discovered that goblins kidnapped the merchant.

Session 6
We rescued the merchant.
```

This information must remain available after subsequent progress is added.

Updating the Quest description is unsuitable because it destroys or obscures historical information.

A separate historical object is therefore required.

## 2. Decision

`QuestProgress` is a first-class historical domain object.

Each `QuestProgress` record:

* belongs to exactly one Quest,
* belongs to exactly one Session,
* contains a human-readable description,
* represents one historical progress entry,
* is immutable after creation.

The Quest stores the current state.

`QuestProgress` stores the history that led to that state.

## 3. Schema

```text
QuestProgress
────────────────────────────────────────
id                  UUID / integer    PK

quest_id            UUID / integer    FK → Quest
session_id          UUID / integer    FK → Session

description         TEXT              NOT NULL

created_at          DATETIME          NOT NULL
```

## 4. Field semantics

### `id`

Stable unique identifier.

It must not change after creation.

### `quest_id`

The Quest to which the progress belongs.

Relationship:

```text
Quest 1 ─────── N QuestProgress
```

Every progress record must belong to exactly one Quest.

### `session_id`

The Session during which this progress occurred or was recorded.

Relationship:

```text
Session 1 ─────── N QuestProgress
```

Every progress record must belong to exactly one Session.

This allows the journal to answer:

> During which session did this part of the Quest happen?

### `description`

Human-readable description of what happened.

Example:

```text
Found tracks leading from the merchant's cart toward the abandoned mine.
```

The description is historical information.

It should describe an observation, discovery, decision, achievement, setback, or other meaningful progress related to the Quest.

### `created_at`

Timestamp at which the progress record was created.

The order of progress should primarily be determined by Session chronology and `created_at`.

## 5. Lifecycle

`QuestProgress` has a deliberately simple lifecycle:

```text
created
  ↓
historical / immutable
```

There are no status values.

There is no:

```text
ACTIVE
COMPLETED
FAILED
```

on `QuestProgress`.

Those statuses belong to `Quest`.

A progress record is never converted into another state.

## 6. Immutability

Once created, a QuestProgress record should not normally be edited or deleted.

The intended operation is:

```text
new information
    ↓
new QuestProgress
```

rather than:

```text
old QuestProgress
    ↓
overwrite with new information
```

This preserves the history of the campaign.

If an accidental entry needs correction in a future version, correction mechanisms should be designed explicitly rather than silently modifying historical data.

## 7. Command

### Add progress

```text
!progress-quest <identifier> description="..."
```

The command:

1. Resolves the current Campaign.
2. Resolves the current Session.
3. Resolves the Quest.
4. Verifies that the Quest belongs to the current Campaign.
5. Creates a `QuestProgress`.
6. Associates it with:

   * the Quest,
   * the current Session.
7. Returns the newly created progress entry.

Example:

```text
!progress-quest 42 description="Found the entrance to the goblin hideout."
```

Result:

```text
Quest: Find the Missing Merchant

Session: #5

Progress added:
"Found the entrance to the goblin hideout."
```

## 8. Active Quest requirement

Progress should only be added to an `ACTIVE` Quest in the MVP.

Therefore:

```text
ACTIVE
    → progress allowed

COMPLETED
    → progress rejected

FAILED
    → progress rejected
```

Reason: a completed or failed Quest represents a closed lifecycle.

If the product later needs to record post-completion consequences, this should be handled as a deliberate extension rather than silently allowing modifications to a closed Quest.

## 9. Quest details integration

`/quest-details` retrieves all progress records for the Quest:

```text
Quest
    ↓
QuestProgress[]
```

Example:

```text
Find the Missing Merchant
Status: ACTIVE

Quest giver:
Mayor Menhemes

Received:
Otari Town Hall

Started:
Session #3

Description:
Find the missing merchant.

Progress
────────────────────────────────────────
Session #3
Mayor asked us to investigate the disappearance.

Session #4
Found the merchant's cart.

Session #5
Discovered that the merchant was taken underground.

Session #6
Found the entrance to the underground tunnels.
```

Progress must be displayed chronologically.

## 10. Relationship to Session

QuestProgress is associated with the Session in which the progress was recorded.

This means the same Quest can have progress records across many Sessions:

```text
Quest
 │
 ├── Progress → Session 3
 ├── Progress → Session 4
 ├── Progress → Session 5
 └── Progress → Session 6
```

The Quest therefore remains independent of any single Session.

## 11. Relationship to JournalEvent

`QuestProgress` and `JournalEvent` are intentionally separate.

### QuestProgress

Answers:

> What happened that is relevant to this Quest?

### JournalEvent

Answers:

> What else happened during the Session that is worth remembering?

Example:

```text
Session #5

JournalEvent:
"The party entered the abandoned mine."

QuestProgress → Find the Missing Merchant:
"The party found evidence that the merchant was taken underground."

JournalEvent:
"Thalia discovered an ancient dwarven inscription."
```

Not every JournalEvent belongs to a Quest.

Not every Quest-related detail needs to become a general JournalEvent.

The two records may describe related occurrences but have different purposes.

## 12. Relationship to Quest status

Adding progress does not automatically change the Quest status.

For example:

```text
Quest.status = ACTIVE

/progress-quest
"Found the merchant."

Quest.status remains:
ACTIVE
```

The Quest becomes completed only through:

```text
/complete-quest
```

Likewise, a Quest becomes failed only through:

```text
/fail-quest
```

This prevents the bot from attempting to infer game state from natural-language descriptions.

## 13. No automatic progress extraction

The MVP must not attempt to automatically infer QuestProgress from:

* Discord chat,
* JournalEvent,
* Roll20 data,
* recordings,
* transcription,
* AI.

Those features belong to later roadmap phases.

During the manual journal phase, players explicitly create progress entries.

## 14. Integrity rules

The implementation must enforce:

```text
QuestProgress.quest_id → existing Quest

QuestProgress.session_id → existing Session
```

The Quest and Session must belong to the same Campaign.

This prevents accidentally associating a progress record with:

```text
Quest from Campaign A
+
Session from Campaign B
```

## 15. Non-goals

The MVP does not include:

* automatic progress generation,
* automatic summarization,
* progress categories,
* progress severity,
* progress status,
* progress editing,
* progress deletion,
* automatic Quest completion,
* automatic Quest failure,
* AI-generated progress,
* user ownership.

## 16. Consequences

The Quest remains small and queryable while its history can grow indefinitely.

The model supports the desired player experience:

```text
/list-quests active
        ↓
choose Quest
        ↓
!quest-details <identifier>
        ↓
Quest metadata
+
start session
+
QuestProgress history
```

The design also preserves raw historical information required for future journal generation and AI processing.
