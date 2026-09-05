# ADR-005: JournalEvent Domain and Lifecycle

**Status:** Accepted
**Date:** 2026-09-05

## 1. Context

Not every important event during a Session belongs to a Quest.

Examples:

```text
The party discovered an ancient shrine.

Thalia found an old dwarven inscription.

The party defeated a group of giant rats.

A player learned an important piece of lore.
```

These events are still valuable for the campaign journal.

They therefore require a separate object from `QuestProgress`.

`JournalEvent` represents noteworthy historical information associated with a Session but not necessarily with a specific Quest.

## 2. Decision

`JournalEvent` is a first-class domain object associated with exactly one Session.

It is independent from Quest.

A JournalEvent does not require a Quest relationship.

Quest-specific progress is represented by `QuestProgress`, not by `JournalEvent`.

## 3. Schema

```text
JournalEvent
────────────────────────────────────────
id                  UUID / integer    PK

session_id          UUID / integer    FK → Session

description         TEXT              NOT NULL

created_at          DATETIME          NOT NULL
```

## 4. Field semantics

### `id`

Stable unique identifier.

It must not change after creation.

### `session_id`

The Session during which the event occurred or was recorded.

Relationship:

```text
Session 1 ─────── N JournalEvent
```

### `description`

Human-readable description of the event.

Example:

```text
The party discovered an ancient shrine beneath the ruins.
```

The field is intentionally free-form in MVP.

No event type/category system is required.

### `created_at`

Timestamp at which the event was recorded.

## 5. Purpose

JournalEvent provides the general Session history.

Example:

```text
Session #7
────────────────────────────────────────

JournalEvent
The party entered the abandoned temple.

JournalEvent
Thalia discovered an ancient dwarven inscription.

JournalEvent
The party fought three skeletons.

JournalEvent
The party discovered a hidden chamber.
```

These events remain useful even when none of them is related to a Quest.

## 6. Relationship to QuestProgress

`JournalEvent` and `QuestProgress` intentionally have different responsibilities.

```text
                    Session
                    /      \
                   /        \
                  ▼          ▼
        JournalEvent    QuestProgress
                            │
                            ▼
                          Quest
```

### JournalEvent

Session-level information.

```text
"What happened during this session?"
```

### QuestProgress

Quest-level historical information.

```text
"What happened to this particular quest?"
```

The MVP does not introduce a direct relationship between the two.

If the same event is relevant both to the Session journal and to a Quest, it may be represented by both records.

Example:

```text
JournalEvent:
"The party found the missing merchant alive."

QuestProgress → Find the Missing Merchant:
"The party found the missing merchant alive."
```

This duplication is acceptable because the objects serve different query and presentation purposes.

## 7. Lifecycle

JournalEvent follows a simple lifecycle:

```text
created
  ↓
historical / immutable
```

Once created, it should not normally be modified or deleted.

The MVP does not introduce event statuses.

## 8. Commands

The basic management command is:

```text
!add-journal-event description="..."
```

The command:

1. Resolves the current Campaign.
2. Resolves the current Session.
3. Creates a `JournalEvent`.
4. Associates it with the current Session.
5. Stores the description and timestamp.

Example:

```text
/add-journal-event The party discovered an ancient shrine beneath the ruins.
```

Result:

```text
Journal event added to Session #7.
```

### Read/listing

Journal events should be retrievable as part of Session journal/details functionality.

The exact Session command naming is defined by the Session domain.

For MVP, no separate complex filtering system is required.

## 9. Relationship to Campaign

JournalEvent does not need a direct `campaign_id`.

The Campaign can be resolved through:

```text
JournalEvent
    ↓
Session
    ↓
Campaign
```

This avoids redundant ownership data.

The same principle applies to QuestProgress:

```text
QuestProgress
    ↓
Quest / Session
    ↓
Campaign
```

The implementation must nevertheless validate that the referenced objects belong to the same Campaign.

## 10. Relationship to Quest

A JournalEvent does not belong to a Quest.

There is deliberately no:

```text
quest_id
```

in the MVP JournalEvent schema.

Reason:

A JournalEvent is intended to represent information that is independently relevant to the Session journal.

Quest-specific history already has a dedicated representation:

```text
QuestProgress
```

This keeps the two concepts unambiguous.

## 11. Historical preservation

JournalEvent is historical data.

The bot should append new events rather than overwrite previous events.

Example:

```text
Session #8

Event 1:
"The party entered the crypt."

Event 2:
"Kara discovered a hidden passage."

Event 3:
"The party defeated the undead guardian."
```

The existence of Event 3 must not modify Events 1 or 2.

This is important for future session summaries and AI-generated journals.

## 12. No automatic classification

The MVP must not attempt to determine automatically whether an event:

* belongs to a Quest,
* represents Quest progress,
* is important,
* should be deleted,
* should change Quest status.

Those decisions remain explicit user actions during the manual journal phase.

Future transcription/AI phases may generate candidate events, but that is outside this ADR.

## 13. Data integrity

The implementation must enforce:

```text
JournalEvent.session_id → existing Session
```

The referenced Session must belong to the current Campaign when the event is created through the current Campaign context.

A JournalEvent must never reference a Session belonging to another Campaign.

## 14. Non-goals

The MVP does not include:

* event categories,
* event types,
* Quest relationships,
* NPC relationships,
* Location relationships,
* automatic event extraction,
* AI-generated events,
* event importance/ranking,
* event editing workflows,
* event deletion workflows,
* automatic event-to-Quest classification.

## 15. Consequences

The Session journal can contain all important events without forcing every event into a Quest.

The model remains simple:

```text
Campaign
   │
   └── Session
        │
        ├── JournalEvent
        ├── JournalEvent
        ├── QuestProgress → Quest A
        └── QuestProgress → Quest B
```

This provides two complementary views of the same campaign history:

### Session view

```text
What happened during Session #7?
```

→ `JournalEvent[]` + `QuestProgress[]`

### Quest view

```text
What happened while solving Quest X?
```

→ `QuestProgress[]`

This separation is intentionally preserved because the two views serve different user needs.
