# ADR-003: Quest Domain and Lifecycle

**Status:** Accepted
**Date:** 2026-09-05

## 1. Context

The journal bot needs to allow players to quickly answer:

* What quests do we currently have?
* Which quests have been completed?
* Which quests have failed?
* Who gave us a quest?
* Where did we receive it?
* During which session did we receive it?
* What is the current state of the quest?
* What happened during the process of completing it?

A Quest can span multiple game sessions. Therefore, a Quest must not belong to a single Session.

The Quest itself represents the **current state and identity of a task**. Historical information about the task is stored separately in `QuestProgress`.

The Quest belongs to a Campaign.

## 2. Decision

A Quest is a first-class domain object belonging to a Campaign.

The Quest stores:

* identity,
* basic descriptive information,
* quest giver,
* location where the quest was received,
* session in which the quest was started,
* current lifecycle status,
* lifecycle timestamps.

Historical progress is not stored in the Quest description. It is represented by separate `QuestProgress` records.

## 3. Quest schema

```text
Quest
────────────────────────────────────────
id                  UUID / integer    PK
campaign_id         UUID / integer    FK → Campaign

title               VARCHAR / TEXT    NOT NULL
description         TEXT              NULL

quest_giver         TEXT              NULL
received_at_location TEXT             NULL
started_session_id  UUID / integer    FK → Session, NOT NULL

status              ENUM              NOT NULL

created_at          DATETIME          NOT NULL
closed_at           DATETIME          NULL
```

### Field semantics

#### `id`

Stable, unique Quest identifier.

The ID must never change after creation.

It is used by commands such as:

```text
!quest-details <identifier>
!update-quest <identifier> [title="..."] [description="..."]
!complete-quest <identifier>
!fail-quest <identifier>
!progress-quest <identifier> description="..."
```

The bot may also allow title-based lookup where the title uniquely identifies a Quest.

#### `campaign_id`

The Campaign to which the Quest belongs.

A Quest cannot belong to multiple Campaigns.

Relationship:

```text
Campaign 1 ─────── N Quest
```

#### `title`

Human-readable name of the Quest.

Example:

```text
Find the Missing Merchant
```

It can be changed through `!update-quest`.

Changing the title does not change the Quest ID.

#### `description`

Description of the task itself.

Example:

```text
Find the missing merchant and return him safely to Otari.
```

This field represents the Quest definition, not its history.

It must not be overwritten whenever progress is made.

#### `quest_giver`

Name of the NPC, organization, or other entity that gave the Quest.

Example:

```text
Mayor Menhemes
```

For MVP this is plain text.

Do not introduce an NPC domain object solely for this field.

A future version may replace it with:

```text
quest_giver_id → NPC
```

without changing the overall Quest lifecycle.

#### `received_at_location`

Location where the party received the Quest.

Example:

```text
Otari Town Hall
```

The field intentionally describes the **location where the quest was received**, rather than the current or general location associated with the Quest.

This avoids ambiguity.

For MVP it is plain text.

A future Location domain can replace it if required.

#### `started_session_id`

Session in which the Quest was created / received by the party.

The field is required. Every Quest must have a `started_session_id`.

Relationship:

```text
Session 1 ─────── N Quest
```

This field is required for the journal to answer:

> During which session did we get this quest?

A Quest may span many later Sessions.

`started_session_id` therefore does not represent the Quest's entire lifetime.
The referenced Session must belong to the same Campaign as the Quest.

#### `status`

Current lifecycle state.

Allowed values:

```text
ACTIVE
COMPLETED
FAILED
```

No `ABANDONED` status is used.

#### `created_at`

Timestamp at which the Quest was created.

#### `closed_at`

Timestamp at which the Quest entered a terminal state.

Rules:

```text
ACTIVE:
    closed_at IS NULL

COMPLETED:
    closed_at IS NOT NULL

FAILED:
    closed_at IS NOT NULL
```

## 4. Quest lifecycle

A Quest starts as:

```text
ACTIVE
```

and remains active until explicitly completed or failed.

Allowed transitions:

```text
             ┌──────────────┐
             │    ACTIVE    │
             └──────┬───────┘
                    │
             ┌──────┴───────┐
             ▼              ▼
       ┌───────────┐   ┌────────┐
       │ COMPLETED │   │ FAILED │
       └───────────┘   └────────┘
```

Terminal states cannot be changed in MVP.

There is no `!reopen-quest` command.

If reopening becomes necessary later, it should be introduced as an explicit domain decision rather than implicitly allowed.

## 5. Commands

### Create

```text
!create-quest title="..." description="..." [quest_giver="..."]
    [received_at_location="..."]
```

Behavior:

1. Resolve the current Campaign.
2. Resolve the current Session.
3. Create Quest.
4. Set:

   * `campaign_id = current_campaign_id`
   * `started_session_id = current_session_id`
   * `status = ACTIVE`
   * `created_at = now`
   * `closed_at = NULL`
5. Return the created Quest.

If no Campaign is selected:

```text
No campaign is currently selected. Use !use-campaign <id> first.
```

If no Session is selected, the command must fail clearly.

The bot must not guess the Campaign or Session.

### Update

```text
!update-quest <identifier> [title="..."] [description="..."]
    [quest_giver="..."] [received_at_location="..."]
```

Updates Quest metadata only.

It must not modify:

* `id`
* `campaign_id`
* `started_session_id`
* historical `QuestProgress`
* `created_at`

Updating the Quest does not create a progress record.

### Read

```text
!quest-details <identifier>
```

The command displays at minimum:

```text
Quest title
Status
Quest giver
Received at location
Started in session
Description
Progress history
```

Progress history is retrieved from `QuestProgress`.

The output should present progress in chronological order.

### List

```text
!list-quests status="active"
!list-quests status="completed"
!list-quests status="failed"
!list-quests status="finished"
!list-quests status="all"
```

Semantics:

```text
active
    status = ACTIVE

completed
    status = COMPLETED

failed
    status = FAILED

finished
    status IN (COMPLETED, FAILED)

all
    all quests belonging to the current Campaign
```

The default scope is the current Campaign.

### Complete

```text
!complete-quest <identifier>
```

Behavior:

```text
status = COMPLETED
closed_at = now()
```

The Quest remains readable.

The Quest is not deleted.

### Fail

```text
!fail-quest <identifier>
```

Behavior:

```text
status = FAILED
closed_at = now()
```

The Quest remains readable.

The Quest is not deleted.

### Progress

```text
!progress-quest <identifier> description="..."
```

This command is formally defined in ADR-004.

It creates a new historical `QuestProgress` record and does not modify the Quest description.

## 6. Quest context resolution

Quest commands operate within the current Campaign and, where required, current Session.

Campaign context is resolved through `ServerContext`.

Conceptually:

```text
Discord Guild
    ↓
ServerContext
    ↓
current_campaign_id
    ↓
Campaign
    ↓
Quest
```

For commands creating progress:

```text
Discord Guild
    ↓
ServerContext
    ↓
current_campaign_id
    ↓
Campaign
    ↓
current_session_id
    ↓
Session
    ↓
QuestProgress
```

The exact storage and resolution mechanism for the current Session is defined by the Session domain.

The bot must never infer a Campaign or Session from the Quest title or from historical records.

## 7. Historical data

Quest metadata and Quest history are separate.

The following is intentionally not stored in `Quest.description`:

```text
"We found the merchant's cart.
Then we discovered the goblin cave.
Then we rescued the merchant."
```

Instead:

```text
Quest.description:
"Find the missing merchant."

QuestProgress:
Session 3 → "Found the merchant's cart."
Session 4 → "Discovered the goblin cave."
Session 5 → "Rescued the merchant."
```

This preserves the original Quest definition and the complete history.

## 8. Quest objectives

Quest objectives are a low-priority enhancement and are **not implemented**.

They will not be implemented in the current MVP due to time constraints.
Quest objectives are therefore deferred to a future, explicitly scoped
enhancement rather than being part of the current Quest contract.

If implemented in a future version, objectives could be modeled conceptually as:

```text
Quest 1 ─────── N QuestObjective
```

Example:

```text
Quest: Rescue the Merchant

Objectives:
[✓] Find the merchant's location
[✓] Locate the merchant
[ ] Rescue the merchant
[ ] Return the merchant to Otari
```

This future concept does not replace `QuestProgress`.

If introduced later, the distinction would be:

```text
QuestObjective = what needs to be done
QuestProgress  = what happened
```

Objective commands are not required for the initial Quest command set unless explicitly implemented as a separate feature.

## 9. Integrity rules

The implementation must enforce:

```text
Quest.campaign_id → existing Campaign

Quest.started_session_id → existing Session

Quest.started_session_id → Session.campaign_id = Quest.campaign_id

Quest.status = ACTIVE
    → closed_at IS NULL

Quest.status IN (COMPLETED, FAILED)
    → closed_at IS NOT NULL
```

A Quest must not be deleted as part of normal lifecycle management.

Historical QuestProgress must remain available after completion or failure.

## 10. Non-goals

The MVP does not include:

* Quest reopening
* Quest deletion
* Quest objectives; deferred as a low-priority enhancement and not implemented
  in the MVP due to time constraints
* Quest sharing between Campaigns
* NPC domain integration
* Location domain integration
* automatic status changes based on events
* AI-generated Quest descriptions
* automatic Quest detection
* automatic Quest completion detection
* permissions / roles
* user-specific Quest ownership

## 11. Consequences

This design makes the common journal queries simple:

```text
!list-quests active
```

can query the current Campaign for:

```text
status = ACTIVE
```

and:

```text
!quest-details <id>
```

can combine:

```text
Quest
+
started Session
+
QuestProgress
+
QuestObjective
```

The Quest remains a small and stable domain object while historical information can grow independently.

This also provides a clean foundation for future AI-generated summaries because the source data is preserved as structured historical records rather than being repeatedly overwritten.
