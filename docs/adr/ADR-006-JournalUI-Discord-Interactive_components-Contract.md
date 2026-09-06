# ADR-006: Journal UI — Discord Interactive Components Contract

**Status:** Accepted
**Date:** 2026-09-06

## 1. Purpose

`!journal` is an interactive panel for browsing and managing the campaign journal.

The panel should primarily allow users to:

* quickly view the current campaign and session,
* browse quests,
* filter quests by status,
* open quest details,
* view `QuestProgress` history,
* add `QuestProgress` through the UI,
* complete a quest as `COMPLETED` or `FAILED`,
* browse sessions,
* open session details together with journal events.

Interaction is primarily handled through Discord Components. Text commands remain an alternative way of executing domain operations.

---

# 2. Main UI Principle

`!journal` sends a single message containing the current view.

Subsequent button clicks:

1. are handled by the component handler,
2. read data from the database,
3. perform an action or change the view,
4. render the same message again.

Flow:

```text
User
 │
 │ !journal
 ▼
Journal Dashboard
 │
 ├── Quests ───────────────► Quest List
 │                              │
 │                              ├── Quest A ─► Quest Details
 │                              │                 │
 │                              │                 ├── Add Progress
 │                              │                 ├── Complete
 │                              │                 └── Fail
 │                              │
 │                              └── Quest B ─► Quest Details
 │
 └── Sessions ─────────────► Session List
                                │
                                └── Session ─► Session Details
```

A new message is not created for every navigation step. The panel is updated by editing the existing message.

---

# 3. Views

The MVP contains the following views:

```text
JournalDashboard
    │
    ├── QuestList
    │       │
    │       └── QuestDetails
    │
    └── SessionList
            │
            └── SessionDetails
```

## 3.1. Journal Dashboard

View opened by:

```text
!journal
```

Displays:

```text
┌─────────────────────────────────────────────┐
│ JOURNAL                                     │
│                                             │
│ Campaign: Abomination Vaults                │
│ Session: #12 — Into the Depths              │
│                                             │
│ Quests                                      │
│   Active       4                            │
│   Completed    7                            │
│   Failed       1                            │
│                                             │
│ Recent Activity                             │
│   • Found the hidden entrance               │
│   • Talked to the guard                     │
│   • Recovered the missing key               │
│                                             │
│ [ Quests ]  [ Sessions ]                    │
└─────────────────────────────────────────────┘
```

The dashboard is intended for navigation rather than as a full report.

### Components

```text
[ Quests ]
[ Sessions ]
```

The dashboard may also contain a short `Recent Activity` section with a maximum of a few recent entries.

---

# 4. Quest List

The view displays quests belonging to the current campaign.

```text
┌─────────────────────────────────────────────┐
│ QUESTS                                      │
│                                             │
│ [ All ] [ Active ] [ Completed ] [ Failed ]│
│                                             │
│ ACTIVE                                      │
│                                             │
│ ▸ Find the Missing Scout                    │
│   Quest giver: Captain Arven                │
│                                             │
│ ▸ Investigate the Old Ruins                 │
│   Quest giver: Mira                         │
│                                             │
│ ▸ Deliver the Letter                        │
│   Quest giver: Mayor                        │
│                                             │
│                 [ ◀ ] 1/2 [ ▶ ]             │
│                                             │
│ [ ← Back ]                                  │
└─────────────────────────────────────────────┘
```

The list does not display full quest descriptions. Its purpose is to make it easy to find the relevant quest.

### Filters

Supported filters:

```text
all
active
completed
failed
```

`finished` is represented by `completed + failed` and may be used as an alias by the domain command. The UI only needs the four basic tabs.

### Pagination

The list uses:

```text
[ ◀ ] <page>/<pages> [ ▶ ]
```

The page number is part of the `custom_id`.

---

# 5. Quest Details

Detailed view of a single quest.

`QuestProgress` is the mechanism used to track the quest's history and progress.

```text
┌─────────────────────────────────────────────┐
│ FIND THE MISSING SCOUT                      │
│                                             │
│ Status: ACTIVE                              │
│                                             │
│ Quest giver: Captain Arven                  │
│ Received at: Absalom Guard House            │
│ Started in: Session #12                     │
│                                             │
│ Description                                 │
│ The captain asked the party to locate       │
│ a missing scout...                          │
│                                             │
│ Progress                                    │
│                                             │
│ Session #12                                 │
│ • Party discovered tracks near the ruins.  │
│                                             │
│ Session #13                                 │
│ • Tracks led to an underground passage.    │
│                                             │
│ [ + Progress ] [ Complete ] [ Fail ]        │
│                                             │
│ [ ← Back ]                                  │
└─────────────────────────────────────────────┘
```

For a completed quest:

```text
Status: COMPLETED
```

or:

```text
Status: FAILED
```

The complete `QuestProgress` history remains visible for closed quests.

`QuestProgress` entries provide the historical path of the quest. They can describe:

* actions taken by the party,
* discoveries,
* clues,
* changes in the quest situation,
* completed steps,
* important developments,
* other information relevant to tracking the quest.

There is no separate objective model. If something needs to be tracked as part of a quest, it is recorded through `QuestProgress`.

---

# 6. Session List

The view displays sessions belonging to the current campaign.

```text
┌─────────────────────────────────────────────┐
│ SESSIONS                                    │
│                                             │
│ ▸ Session #13 — The Hidden Passage          │
│   2026-08-28                                │
│                                             │
│ ▸ Session #12 — Into the Depths             │
│   2026-08-21                                │
│                                             │
│ ▸ Session #11 — The Old Ruins               │
│   2026-08-14                                │
│                                             │
│                 [ ◀ ] 1/2 [ ▶ ]             │
│                                             │
│ [ ← Back ]                                  │
└─────────────────────────────────────────────┘
```

Sessions are displayed in descending order by date/session number.

---

# 7. Session Details

The session details view displays events associated with the selected session.

```text
┌─────────────────────────────────────────────┐
│ SESSION #13                                 │
│ The Hidden Passage                          │
│                                             │
│ Date: 2026-08-28                            │
│                                             │
│ Journal Events                              │
│ • Party discovered a hidden entrance.      │
│ • The old inscription was translated.      │
│ • A hostile patrol was encountered.        │
│                                             │
│ Quest Progress                              │
│                                             │
│ Find the Missing Scout                      │
│ • Tracks led to an underground passage.    │
│                                             │
│ Investigate the Old Ruins                  │
│ • The inscription revealed a hidden room.  │
│                                             │
│ [ ← Back ]                                  │
└─────────────────────────────────────────────┘
```

The session displays two types of information:

```text
Session
│
├── JournalEvent
│
└── QuestProgress
```

This allows users to see both general session events and progress related to specific quests.

---

# 8. Navigation

Complete UI flow:

```text
                    ┌───────────────────┐
                    │ Journal Dashboard │
                    └─────────┬─────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
          ┌─────────────┐           ┌─────────────┐
          │ Quest List  │           │Session List │
          └──────┬──────┘           └──────┬──────┘
                 │                         │
                 ▼                         ▼
          ┌─────────────┐           ┌───────────────┐
          │Quest Details│           │Session Details│
          └──────┬──────┘           └───────────────┘
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
  + Progress  Complete    Fail
```

The `Back` button always leads to the logical parent:

```text
Quest Details
      │
      ▼
Quest List
      │
      ▼
Journal Dashboard
```

and:

```text
Session Details
      │
      ▼
Session List
      │
      ▼
Journal Dashboard
```

---

# 9. `custom_id` Contract

A component's `custom_id` is the stable identifier of a UI action.

Format:

```text
j:<resource>:<action>:<arguments...>
```

The `j` prefix identifies Journal components.

## Dashboard

```text
j:home
```

Returns to the dashboard.

---

## Quest List

```text
j:q:list:<filter>:<page>
```

Examples:

```text
j:q:list:all:0
j:q:list:active:0
j:q:list:completed:1
j:q:list:failed:0
```

Actions:

```text
j:q:list:active:0
j:q:list:active:1
j:q:list:active:2
```

represent pages 1, 2, and 3 of the active quest list respectively, using zero-based page indexing internally.

---

## Open Quest

```text
j:q:view:<quest_id>
```

Example:

```text
j:q:view:056he0
```

`quest_id` is the domain `Quest` identifier.

---

## Quest Details — Actions

Add progress:

```text
j:q:progress:<quest_id>
```

Complete:

```text
j:q:complete:<quest_id>:<filter>:<page>
```

Fail:

```text
j:q:fail:<quest_id>:<filter>:<page>
```

Back:

```text
j:q:back:<filter>:<page>
```

Example:

```text
j:q:back:active:0
```

This preserves the previous filter and page when returning to the quest list.

---

# 10. Session List

Format:

```text
j:s:list:<page>
```

Examples:

```text
j:s:list:0
j:s:list:1
```

---

# 11. Session Details

Open session:

```text
j:s:view:<session_id>
```

Back:

```text
j:s:back:<page>
```

Example:

```text
j:s:back:0
```

---

# 12. Data Passed Between Views

The UI passes only the minimum state required to reconstruct a view.

## Quest

```text
quest_id
filter
page
```

## Session

```text
session_id
page
```

The full quest or session object is not stored in `custom_id`.

Detailed data is loaded from the database each time.

Flow:

```text
Discord Component
       │
       │ custom_id
       ▼
Component Handler
       │
       ├── parse resource/action/id
       │
       ├── read current context
       │
       ├── query database
       │
       └── render view
               │
               ▼
       edit original message
```

This ensures that the UI reflects current data even if another user changes the data between interactions.

---

# 13. Current Campaign and Current Session

The UI uses the existing `ServerContext`.

```text
Discord Guild
      │
      ▼
ServerContext
      │
      ├── current_campaign_id
      │
      └── current session context
```

`current campaign` is required for campaign-scoped journal operations.

`current session` is required for operations that create events associated with the current session.

---

# 14. Current Campaign Requirements

The following actions require a `current campaign`:

| Action          | Current Campaign |
| --------------- | ---------------- |
| `!journal`      | YES              |
| Quest List      | YES              |
| Quest Details   | YES              |
| Session List    | YES              |
| Session Details | YES              |
| Complete Quest  | YES              |
| Fail Quest      | YES              |
| Add Progress    | YES              |

If there is no current campaign, display a clear message:

```text
No campaign is currently selected.
Use !use-campaign <id> first.
```

---

# 15. Current Session Requirements

A `current session` is required for operations that create `QuestProgress`.

| Action          | Current Session |
| --------------- | --------------- |
| Dashboard       | NO              |
| Quest List      | NO              |
| Quest Details   | NO              |
| Session List    | NO              |
| Session Details | NO              |
| Add Progress    | YES             |
| Complete Quest  | NO              |
| Fail Quest      | NO              |

Every `QuestProgress` belongs to a specific session.

For `+ Progress`, the handler:

1. retrieves the current campaign,
2. retrieves the current session,
3. verifies that the quest belongs to the current campaign,
4. creates `QuestProgress` with `session_id = current_session.id`.

If there is no current session, the modal is not opened. Display:

```text
No session is currently selected.
Select a current session before adding quest progress.
```

---

# 16. Add Progress — Modal

Clicking:

```text
j:q:progress:<quest_id>
```

opens a Discord Modal.

Layout:

```text
Quest Details
      │
      │ [+ Progress]
      ▼
┌───────────────────────────────────────┐
│ Add Quest Progress                    │
│                                       │
│ What happened?                        │
│ ┌───────────────────────────────────┐ │
│ │ Party discovered that...          │ │
│ │                                   │ │
│ └───────────────────────────────────┘ │
│                                       │
│              [ Save Progress ]        │
└───────────────────────────────────────┘
```

Modal custom ID:

```text
j:m:progress:<quest_id>
```

Text input:

```text
custom_id = description
```

After submission:

```text
Modal Submit
     │
     ▼
current campaign
     │
     ▼
current session
     │
     ▼
Quest
     │
     ▼
QuestProgress
```

The panel then returns to:

```text
Quest Details
```

and displays the new entry.

---

# 17. Complete Quest

Button:

```text
j:q:complete:<quest_id>:<filter>:<page>
```

opens an action confirmation.

```text
┌───────────────────────────────────────┐
│ Complete Quest?                       │
│                                       │
│ Find the Missing Scout                │
│                                       │
│ [ Confirm ] [ Cancel ]                │
└───────────────────────────────────────┘
```

After confirmation:

```text
Quest.status = COMPLETED
Quest.closed_at = now
```

The `Quest Details` view is then rendered again.

For a `COMPLETED` quest, the action buttons are no longer displayed.

---

# 18. Fail Quest

Analogously:

```text
j:q:fail:<quest_id>:<filter>:<page>
```

Confirmation:

```text
┌───────────────────────────────────────┐
│ Fail Quest?                           │
│                                       │
│ Find the Missing Scout                │
│                                       │
│ [ Confirm ] [ Cancel ]                │
└───────────────────────────────────────┘
```

After confirmation:

```text
Quest.status = FAILED
Quest.closed_at = now
```

The panel is rendered again.

---

# 18.1. Confirmation routing

Complete and Fail are two-step actions. The first button click must not change
the Quest. It replaces the current panel content with a confirmation view in
the same Discord message:

```text
[ Confirm ] [ Cancel ]
```

The confirmation buttons use:

```text
j:q:confirm-complete:<quest_id>:<filter>:<page>
j:q:confirm-fail:<quest_id>:<filter>:<page>
j:q:cancel:<quest_id>:<filter>:<page>
```

`filter` and `page` preserve the Quest List state from which the Quest Details
view was opened. They use the same values and zero-based page indexing defined
for `j:q:list:<filter>:<page>`.

When a confirmation button is clicked, the handler must:

1. Resolve the current guild Campaign.
2. Load the Quest by ID and verify that it belongs to that Campaign.
3. Re-read the Quest status from the database.
4. Call the existing Complete Quest or Fail Quest domain operation.
5. Reload the Quest.
6. Render Quest Details in the same panel message.

The UI must not implement a separate lifecycle operation.

The current Session is not required for completing or failing a Quest.

The confirmation is evaluated against current database state, not the state
shown when it was opened. If the Quest is missing, belongs to another
Campaign, or is already terminal, the handler must not perform an opposing or
duplicate transition. It must display the current domain error or Quest
Details instead.

Terminal states remain terminal. A stale Complete confirmation must not change
`FAILED` to `COMPLETED`, and a stale Fail confirmation must not change
`COMPLETED` to `FAILED`.

Cancel performs no domain mutation. It reloads the Quest and renders Quest
Details in the same panel message, preserving the stored `filter` and `page`
for the Back action.

Normal navigation, confirmation, and cancellation update the original
`!journal` panel message and do not create a new navigation message. If the
original panel cannot safely be rendered, validation and stale-interaction
errors may be sent as ephemeral responses. Every Discord interaction must be
acknowledged exactly once.

# 19. Quest Selection Button

Each quest in the quest list is represented by a button:

```text
j:q:view:<quest_id>
```

Example:

```text
[ Find the Missing Scout ]
[ Investigate the Old Ruins ]
[ Deliver the Letter ]
```

Each button opens `Quest Details`.

---

# 20. Session Selection Button

Each session in the session list uses:

```text
j:s:view:<session_id>
```

Example:

```text
[ Session #13 — The Hidden Passage ]
[ Session #12 — Into the Depths ]
[ Session #11 — The Old Ruins ]
```

---

# 21. Pagination

Pagination buttons use:

```text
j:q:list:<filter>:<page>
j:s:list:<page>
```

For example:

```text
[ ◀ ] 2/4 [ ▶ ]

previous:
j:q:list:active:0

next:
j:q:list:active:2
```

The renderer determines whether `Previous` and `Next` are enabled.

---

# 22. Rendering Model

Each view should have its own renderer.

Suggested structure:

```text
JournalRenderer
│
├── render_dashboard()
│
├── render_quest_list(filter, page)
│
├── render_quest_details(quest_id)
│
├── render_session_list(page)
│
└── render_session_details(session_id)
```

Renderers return the complete set of elements required to update the message:

```text
View
├── embed/content
└── components
```

The interaction handler is responsible for routing and executing operations; the renderer is responsible for presentation.

---

# 23. Routing Contract

The component handler interprets `custom_id`.

Example:

```text
j:q:view:056he0
```

is interpreted as:

```text
resource = quest
action   = view
quest_id = 056he0
```

Example:

```text
j:q:list:active:2
```

as:

```text
resource = quest
action   = list
filter   = active
page     = 2
```

Example:

```text
j:q:progress:056he0
```

as:

```text
resource = quest
action   = progress
quest_id = 056he0
```

---

# 24. Data Dependencies

The UI follows the existing domain model:

```text
Campaign
│
├── Session
│   ├── JournalEvent
│   └── QuestProgress
│
└── Quest
    └── QuestProgress
```

For quest details:

```text
Quest
 │
 ├── metadata
 │
 └── QuestProgress[]
          │
          └── Session
```

For session details:

```text
Session
 │
 ├── JournalEvent[]
 │
 └── QuestProgress[]
          │
          └── Quest
```

`QuestProgress` is the historical tracking mechanism for a quest.

---

# 25. Data Update Behavior

Every data-changing action executes a domain operation and then reloads the data for rendering.

Example:

```text
[ + Progress ]
      │
      ▼
Create QuestProgress
      │
      ▼
Reload Quest
      │
      ▼
Render Quest Details
```

The old UI text is not manually patched.

Similarly:

```text
[ Complete ]
      │
      ▼
Complete Quest
      │
      ▼
Reload Quest
      │
      ▼
Render Quest Details
```

---

# 26. Consistency with Existing Commands

The UI is a presentation layer over the existing domain operations.

For example:

```text
!complete-quest
        │
        ▼
CompleteQuestUseCase
        ▲
        │
j:q:complete:<quest_id>:<filter>:<page>
```

and:

```text
!progress-quest
        │
        ▼
CreateQuestProgressUseCase
        ▲
        │
j:m:progress:<quest_id>
```

Domain logic should not be implemented separately for the UI.

---

# 27. Component Contract — Summary

| View            | Component        | `custom_id`                  |
| --------------- | ---------------- | ---------------------------- |
| Dashboard       | Quests           | `j:q:list:all:0`             |
| Dashboard       | Sessions         | `j:s:list:0`                 |
| Quest List      | Filter All       | `j:q:list:all:<page>`        |
| Quest List      | Filter Active    | `j:q:list:active:<page>`     |
| Quest List      | Filter Completed | `j:q:list:completed:<page>`  |
| Quest List      | Filter Failed    | `j:q:list:failed:<page>`     |
| Quest List      | Quest            | `j:q:view:<quest_id>`        |
| Quest List      | Previous         | `j:q:list:<filter>:<page-1>` |
| Quest List      | Next             | `j:q:list:<filter>:<page+1>` |
| Quest List      | Back             | `j:home`                     |
| Quest Details   | Add Progress     | `j:q:progress:<quest_id>`    |
| Quest Details   | Complete         | `j:q:complete:<quest_id>:<filter>:<page>` |
| Quest Details   | Fail             | `j:q:fail:<quest_id>:<filter>:<page>` |
| Quest Details   | Back             | `j:q:back:<filter>:<page>`   |
| Quest Confirmation | Confirm complete | `j:q:confirm-complete:<quest_id>:<filter>:<page>` |
| Quest Confirmation | Confirm fail | `j:q:confirm-fail:<quest_id>:<filter>:<page>` |
| Quest Confirmation | Cancel | `j:q:cancel:<quest_id>:<filter>:<page>` |
| Session List    | Session          | `j:s:view:<session_id>`      |
| Session List    | Previous         | `j:s:list:<page-1>`          |
| Session List    | Next             | `j:s:list:<page+1>`          |
| Session List    | Back             | `j:home`                     |
| Session Details | Back             | `j:s:back:<page>`            |
| Progress Modal  | Modal            | `j:m:progress:<quest_id>`    |

---

# 28. Final User Flow

The most common scenario:

```text
!journal
   │
   ▼
Dashboard
   │
   ▼
[ Quests ]
   │
   ▼
Active Quests
   │
   ▼
[ Find the Missing Scout ]
   │
   ▼
Quest Details
   │
   ▼
[ + Progress ]
   │
   ▼
Modal
   │
   ▼
Save Progress
   │
   ▼
Quest Details
   │
   │
   ├── [ Complete ] ──► confirmation ──► COMPLETED
   │
   └── [ Fail ] ──────► confirmation ──► FAILED
```

Alternative path:

```text
!journal
   │
   ▼
Dashboard
   │
   ▼
[ Sessions ]
   │
   ▼
Session List
   │
   ▼
[ Session #13 ]
   │
   ▼
Session Details
   │
   ├── Journal Events
   │
   └── Quest Progress
```

---

# 29. Visual Reference

The previously generated `!journal` mockup should be treated as **visual inspiration** for:

* information hierarchy,
* panel layout,
* quest presentation,
* navigation buttons,
* quest details layout,
* the overall Discord Components style.

The mockup is a visual reference. This ADR is the source of truth for UI behavior, views, data, and `custom_id` values.

The reference image should be included with the materials provided to the Coding Agents together with this ADR.

---

# 30. MVP Completion Criteria

`!journal` is complete when a user can:

1. open the dashboard,
2. see the current campaign and session,
3. navigate to the quest list,
4. filter quests by status,
5. navigate between pages,
6. open quest details,
7. see quest metadata and `QuestProgress` history,
8. add `QuestProgress` through a Modal,
9. complete a quest as `COMPLETED`,
10. fail a quest as `FAILED`,
11. return to the previous view,
12. navigate to the session list,
13. open session details,
14. see `JournalEvent` and `QuestProgress` associated with the session.

The entire interaction takes place within a single `!journal` panel message, updated through Discord Components.
