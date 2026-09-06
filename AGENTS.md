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
            ├── current_campaign_id ──► Campaign
            │                              │
            │                              ├── Session[]
            │                              ├── Quest[]
            │                              └── future journal objects
            │
            └── current_session_id ───► Session
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
!start-campaign title="..." [description="..."]
!use-campaign <identifier>
!list-campaign
!read-campaign <identifier>
!update-campaign <identifier> [title="..."] [description="..."]
!end-campaign
```

## Command Argument Syntax

All commands use named parameters so values containing spaces, commas, or
other punctuation are unambiguous.

Both forms are supported:

```text
title="Find the missing merchant"
--title "Find the missing merchant"
```

The assignment form and the double-dash form may be mixed in one command.
Quoted values are required when a value contains whitespace. The only
positional parameter is an optional command identifier, which must be first;
all metadata and filter parameters remain named.

Examples:

```text
!start-campaign title="Kingmaker" description="Stolen land"
!use-campaign "Kingmaker"
!update-campaign 42 title="New title"
```

Command parameters are parsed by name. Unknown, duplicated, malformed, or
unexpected positional parameters must be rejected with a usage error. A
parameter omitted from an update is left unchanged; an explicitly supplied
empty value clears nullable metadata where supported.

## `!start-campaign`

Creates a new Campaign.

The newly created campaign becomes the current campaign for the Discord guild.

Creating a new campaign does NOT automatically end an existing campaign.

## `!use-campaign`

Selects a campaign as the current campaign context for the Discord guild.

The campaign may be identified by ID or title.

## `!list-campaign`

Lists available campaigns with at least:

```text
ID
Title
Status
```

The currently selected campaign should ideally be visually identifiable.

## `!read-campaign`

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

## `!update-campaign`

Updates campaign metadata.

Supported fields:

```text
title
description
```

Updating a campaign must not change its ID.

## `!end-campaign`

Ends the currently selected campaign.

Effect:

```text
status = ENDED
ended_at = current timestamp
```

Ending a campaign does not delete its data.

A campaign cannot be ended while it has an active session. The session must be
ended explicitly first.

---

# Campaign Context

The currently selected campaign is persistent state associated with a Discord guild.

It must NOT be stored only in application memory.

Use a `ServerContext` concept/table.

## ServerContext

```text
discord_guild_id
current_campaign_id
current_session_id
updated_at
```

Relationship:

```text
ServerContext.current_campaign_id → Campaign.id
ServerContext.current_session_id → Session.id
```

`current_campaign_id` may be `NULL`.
`current_session_id` may be `NULL`.

The context is scoped to the Discord guild.

For MVP:

> All users on the same Discord guild share the same current campaign.

Do not implement user-specific or channel-specific campaign contexts.

---

# Session

A Session represents one RPG meeting and belongs to exactly one Campaign.
Session data is persistent and must use the existing ORM.

## Session fields

```text
id
campaign_id
number
title
description
status
created_at
played_at
ended_at
```

### Field semantics

* `id` — immutable unique identifier.
* `campaign_id` — required foreign key to Campaign.
* `number` — positive number unique within the campaign.
* `title` — required after creation; generated as `Session <number>` when omitted.
* `description` — optional free-form description of what happened during the session.
* `status` — `ACTIVE` or `ENDED`.
* `created_at` — timestamp when the session record was created.
* `played_at` — actual RPG session date/time; defaults to `created_at` and can be corrected later.
* `ended_at` — timestamp when the session was ended; `NULL` while active.

Integrity rules:

```text
ACTIVE → ended_at IS NULL
ENDED  → ended_at IS NOT NULL
UNIQUE (campaign_id, number)
UNIQUE (campaign_id, title)
At most one ACTIVE session per campaign
```

There must never be two active sessions in one campaign. Starting a session
is rejected if the campaign already has an active session.

## Session Commands

```text
!start-session [title="..."] [description="..."]
!use-session <identifier>
!list-session
!read-session <identifier>
!update-session <identifier> [title="..."] [description="..."]
    [played_at="..."]
!end-session
```

Session creation requires the current campaign context, and the campaign must
be active. Creating a session selects it as the current session for the guild.

Existing sessions can be read, selected, and updated by stable ID or exact
title. Title lookup is scoped to the current campaign and titles must be unique
within that campaign. Session numbers are display-only and are not lookup
identifiers.

Ending a session preserves its data. An ended session can still be read and
selected. Ending a campaign is rejected while any session in that campaign is
active.

Session context is guild-scoped and shared by all users on the guild. Selecting
a session also selects its campaign.

---

# Context Resolution

Commands operating on child objects should resolve their campaign from the current guild context.

Example:

```text
!use-campaign 42

!create-quest title="Find the Witch" description="Investigate the strange events..."
```

The second command must result in:

```text
Quest.campaign_id = 42
```

The user should not have to specify `campaign_id` for every child-object command.

Session-dependent commands add one more resolution step:

```text
Discord guild ID
    ↓
ServerContext.current_session_id
    ↓
Session
    ↓
create/update session child object
```

Selecting a session also selects its campaign. A session must always belong to
the campaign stored in the guild context.

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
Use !use-campaign <id> first.
```

The bot must never guess which campaign the user intended.

---

# Missing Session Context

If:

```text
ServerContext.current_session_id = NULL
```

a command requiring a current session must fail clearly.

Example:

```text
No session is currently selected.
Use !use-session <id or title> first.
```

The bot must never guess which session the user intended.

---

# Ended Campaigns

An ended campaign remains in the database.

It can still be:

* listed,
* read,
* selected as the current campaign.

The MVP does not require:

```text
!delete-campaign
!reopen-campaign
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

# Working Rules for Agents

1. Do not write code outside the currently requested scope.
2. Before introducing a new domain object, clarify its relationship to Campaign.
3. Prefer simple database models suitable for an MVP.
4. Keep IDs stable and use foreign-key relationships between domain objects.
5. Keep Discord-specific context separate from domain objects where practical.
6. Do not use in-memory state as the source of truth for persistent application state.
7. Use the existing ORM for database interactions; keep handwritten SQL to the
   minimum necessary.
8. Do not implement permissions yet.
9. Do not implement recording/transcription/AI/Roll20 functionality yet.
10. Preserve historical journal information where it has future analytical value.
11. When a requirement is ambiguous, identify the ambiguity before making a significant architectural decision.
12. Treat ADRs as project-level architectural decisions.
13. Avoid speculative abstractions that exist only for possible future features.

## Verification

After code changes, run the repository verification commands defined in the
Makefile:

```text
make lint
make coverage-check
```

Run `make install-deps` first only when dependencies are missing or need to be
restored. Do not use `make run` as a verification command because it starts
the Discord bot.

---

# QA Engineering Guide

This section describes how agents acting as QA engineers should verify feature
implementation, check test coverage, and report findings.

## QA scope

QA work must be scoped to the currently implemented feature and the relevant ADRs.
Do not evaluate a feature against future ADRs or future product concepts unless
those items are explicitly in scope for the task.

When verifying an implementation:

* read the relevant ADR or product requirement first,
* inspect the actual implementation in the relevant source files,
* confirm that all in-scope acceptance criteria are implemented,
* confirm that the behaviors are actually tested,
* report only what is implemented, missing, or untested.

Ignore speculative future objects such as recording, transcription, AI-generated
summaries, Roll20 integration, or permissions unless a specific task requests
that scope.

## Verification approach

1. Inspect the feature contract.
   - Identify the relevant ADR and command/object requirements.
   - Check lifecycle rules, persistence rules, context resolution, and user-facing behavior.
2. Inspect the implementation.
   - Review the domain model, repository/store logic, and bot command integration.
   - Confirm whether the feature matches the described contract.
3. Inspect test coverage.
   - Check whether each required behavior has a test asserting it.
   - Look for missing scenarios such as edge cases, invalid inputs, context errors, and lifecycle transitions.
4. Validate the repository.
   - Run the smallest relevant test subset when possible.
   - Run the required project verification commands when needed.
5. Write the report.
   - State clearly what is implemented, missing, and untested.
   - Base claims on evidence from code and test execution.

## What counts as implemented

A feature is considered implemented only when:

* the behavior exists in the code,
* the relevant ADR acceptance criteria are satisfied,
* the expected domain rules are enforced,
* users can exercise the feature through the correct command/API flow,
* the behavior is exercised by tests.

## What counts as not implemented

A feature is not implemented when:

* the relevant object, command, or lifecycle rule is absent,
* the implementation only partially matches the requirement,
* the design is described in a later ADR and therefore intentionally out of scope,
* a required acceptance criterion is missing from the code.

## Test coverage expectations

QA should verify both implementation and tests.

A requirement is considered covered by tests when there is a test asserting the expected behavior.
Examples of important scenarios:

* lifecycle transitions,
* invalid inputs,
* missing campaign/session context,
* ambiguous resolution,
* campaign-scoped lookup,
* persistence and integrity constraints,
* command parsing for named and positional arguments,
* user-visible output for command results.

If a scenario is not explicitly tested, report it as untested.

## Report guidelines

Reports must be concise, evidence-based, and scoped.

A QA report should include:

* feature or ADR under review,
* implementation status,
* implemented acceptance criteria,
* missing acceptance criteria,
* test coverage status,
* verification commands run and results.

### Reporting format

Use direct statements such as:

* "Implemented: ..."
* "Not implemented: ..."
* "Covered by tests: ..."
* "Not covered by tests: ..."
* "Validation: `make coverage-check` passed; `make lint` passed."

### Important rule

Do not include future or unrelated ADRs in the report unless the task explicitly
asks for them. For example, a Quest review should not claim future
`QuestProgress` or `JournalEvent` objects are required unless they are part of the
currently reviewed scope.

## Verification commands

Use the repository verification commands defined in the Makefile:

```text
make lint
make coverage-check
```

Run `make install-deps` first only when dependencies are missing or need to be restored.

Do not use `make run`, because it starts the Discord bot.

## Example QA summary

```text
Implemented: Quest lifecycle and campaign-context handling.
Not implemented: QuestProgress history model and progress-quest command, because they are described in a later ADR and are outside the reviewed scope.
Covered by tests: creation, status transitions, campaign scoping, ambiguity checks.
Not covered by tests: bot command-level parsing for positional update identifiers.
Validation: `make coverage-check` passed; `make lint` passed.
```

## Final QA rule

QA engineering is based on evidence. Verify the contract, verify the tests, and
report the current state precisely without guessing or expanding scope.

---

# Current Status

The following decisions are already accepted and implemented in the codebase:

```text
Campaign:
    ✓ Defined
    ✓ Database schema defined
    ✓ Lifecycle defined
    ✓ Commands defined
    ✓ Persistent guild-level context defined

Session:
    ✓ Defined in ADR-002
    ✓ Database schema defined
    ✓ Lifecycle defined
    ✓ Commands defined
    ✓ Persistent guild-level context handling implemented

Quest:
    ✓ Defined in ADR-003
    ✓ Database schema defined
    ✓ Lifecycle defined
    ✓ Commands defined
    ✓ Campaign and session context resolution implemented
    ✓ Validation and invariants implemented

QuestProgress:
    ✓ Defined in ADR-004
    ✓ Database schema defined
    ✓ Lifecycle and immutability defined
    ✓ Command support implemented
    ✓ Guild/session context resolution implemented
    ✓ Validation and invariant checks implemented
    ✓ Covered by tests

Journal events:
    ✓ Defined in ADR-005
    ⚠ Not yet implemented in the application code

Recording:
    ☐ Future

Transcription:
    ☐ Future

AI journal generation:
    ☐ Future

Permissions:
    ☐ Post-MVP
```

The project has reached a mature Phase 1 baseline for Campaign, Session, and Quest.
The remaining implemented-in-ADR-but-not-yet-in-code items are future domain
extensions that should be treated as out of scope for current QA verification
unless explicitly requested.

## Maintaining Current Status

Whenever a new feature is implemented and verified:

* update this section in the same change or immediately after verification,
* reflect the feature's actual implementation state,
* distinguish between ADR-defined, implemented, tested, and future work,
* update the relevant domain's checklist and the summary below it,
* do not mark a feature as implemented until its required acceptance criteria
  and tests have been verified.

When a feature is only partially implemented, record the partial state and
identify the remaining gap rather than marking it complete. Keep this section
consistent with the codebase, ADRs, and test suite.
