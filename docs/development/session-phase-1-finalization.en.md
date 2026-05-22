# RETIRED DOCUMENT

# Phase 1 Finalization: Session Domain Reset

## Purpose

This document closes the design loop for **Phase 1: Session Domain Reset**.

It converts the earlier Phase 1 planning documents from recommendation-level guidance into a fixed implementation baseline. After this document, Phase 1 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the `Session` domain shape
- the initial enum set
- the persistence direction
- the repository boundary
- the `SessionService` surface
- the legacy boundary against `task` and `operation`

It should be read together with:

- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 1 Implementation Checklist](D:\Project\Python\Agent\docs\development\session-phase-1-implementation-checklist.en.md)
- [Phase 1 Domain and Service Contract Draft](D:\Project\Python\Agent\docs\development\session-phase-1-domain-and-service-contract.en.md)

## Phase 1 Status

Phase 1 is now **architecturally converged**.

This means:

- the top-level domain reset is settled
- the main unresolved design choices are closed
- coding can begin without reopening the product model

## Replacement Position of Phase 1

Phase 1 is the point where `task` and `operation` are replaced in **architecture terms**.

After Phase 1:

- `session` is the only valid target top-level product model
- `task` and `operation` may still exist in code temporarily
- but they are legacy and no longer define the future runtime contract

Phase 1 does **not** require full removal of legacy command paths from the running product surface.

That replacement is completed in product-entry terms during Phase 2.

## Final Decisions

## 1. Top-Level Product Entity

Final decision:

- `session` is the only top-level user-facing work unit

Not allowed:

- keeping `task` and `operation` as parallel permanent product-facing concepts
- introducing a new compatibility wrapper that hides, but preserves, the old split

## 2. Session Modes

Final decision:

```text
SessionMode
  - normal
  - redteam
```

Meaning:

- `normal` is for general-purpose and temporary work
- `redteam` is for target-oriented persistent security workflows

## 3. Persistence Modes

Final decision:

```text
SessionPersistenceMode
  - ephemeral
  - persistent
```

Default mapping:

- `normal` -> `ephemeral`
- `redteam` -> `persistent`

Rationale:

- this preserves future flexibility without complicating the initial user model

## 4. Session Status Set

Final decision:

```text
SessionStatus
  - draft
  - active
  - paused
  - completed
  - failed
  - cancelled
```

Rationale:

- the set is shared across both `normal` and `redteam`
- it avoids copying the current `task` and `operation` status split directly
- it is simple enough for Phase 1 and expressive enough for future controller work

## 5. Terminal State Policy

Final decision:

- `completed` is terminal
- `cancelled` is terminal
- `failed` is terminal in Phase 1

Not included in Phase 1:

- resuming failed sessions directly

Reason:

- it keeps the first implementation smaller and avoids introducing recovery semantics too early

Any future support for failed-session recovery must be introduced as an explicit later-phase feature.

## 6. Public ID Format

Final decision:

- sessions use public IDs in the `S0001` format

Rules:

- public IDs are assigned by the repository layer
- public IDs are stable
- public IDs are intended for CLI and future UI use

## 7. Target Representation

Final decision:

Phase 1 uses embedded structured JSON targets stored on the session record.

Target structure:

```text
SessionTarget
  kind: SessionTargetKind
  value: str
  note: str | None
```

Target kinds:

- `domain`
- `host`
- `ip`
- `cidr`
- `url`

Storage decision:

- store targets in `targets_json`
- do not create a normalized target table in Phase 1

Rationale:

- Phase 1 prioritizes domain clarity and delivery speed over relational flexibility

## 8. Session Field Set

Final decision:

The Phase 1 `Session` model includes:

```text
Session
  id: str
  public_id: str
  title: str
  goal: str
  mode: SessionMode
  persistence_mode: SessionPersistenceMode
  workspace: str
  status: SessionStatus
  targets: list[SessionTarget]
  target_summary: str | None
  authorization_note: str | None
  created_at: str
  updated_at: str
  closed_at: str | None
  last_error: str | None
  metadata: dict[str, Any]
```

Core rules:

- `title` is required
- `goal` is required
- `mode` is required
- `workspace` is required
- `targets` defaults to `[]`
- `metadata` defaults to `{}`

## 9. Target Summary Policy

Final decision:

- `target_summary` remains a first-class field
- it is derived from targets when omitted
- it exists for UX and list views
- it is not the authoritative target store

## 10. Authorization Note Policy

Final decision:

- `authorization_note` remains a lightweight session field

It is intended for:

- engagement notes
- authorization reminders
- operator context

It is not intended to become a substitute for a future formal authorization model.

## 11. Repository Location

Final decision:

- the repository will live at `src/storage/repositories/sessions.py`

Reason:

- it aligns with the newer repository-oriented runtime organization

## 12. Service Location

Final decision:

- the application service will live at `src/app/session_service.py`

## Final State Transition Rules

Allowed transitions in Phase 1:

```text
draft -> active
draft -> cancelled

active -> paused
active -> completed
active -> failed
active -> cancelled

paused -> active
paused -> failed
paused -> cancelled
```

Disallowed transitions in Phase 1:

```text
failed -> active
failed -> paused
failed -> completed

completed -> any
cancelled -> any
```

Implementation rule:

- invalid transitions must be rejected by `SessionService`

## Final Persistence Contract

## Sessions Table

Phase 1 table shape:

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    mode TEXT NOT NULL,
    persistence_mode TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL,
    target_summary TEXT,
    authorization_note TEXT,
    targets_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    last_error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);
```

Required indexes:

```sql
CREATE INDEX idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX idx_sessions_mode ON sessions(mode);
CREATE INDEX idx_sessions_status ON sessions(status);
```

Optional later work:

- title query optimization
- workspace query optimization

## Serialization Rules

The repository must serialize:

- `targets` to `targets_json`
- `metadata` to `metadata`

Encoding rules:

- JSON
- UTF-8 safe
- `ensure_ascii=False`

## Final Repository Contract

Phase 1 repository surface:

```python
class SessionRepository:
    def create(self, session: Session) -> Session: ...
    def get(self, identifier: str) -> Session | None: ...
    def require(self, identifier: str) -> Session: ...
    def list(
        self,
        *,
        mode: SessionMode | None = None,
        status: SessionStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Session]: ...
    def update(self, session: Session) -> Session: ...
```

Repository behavior rules:

1. `get(identifier)` must accept both internal IDs and public IDs.
2. `create(...)` assigns `public_id` if not already assigned.
3. `list(...)` sorts by most recently updated first.
4. `update(...)` persists the full session row.

## Final SessionService Contract

Phase 1 service surface:

```python
class SessionService:
    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SessionService": ...

    def create_session(
        self,
        *,
        title: str,
        goal: str,
        mode: SessionMode,
        persistence_mode: SessionPersistenceMode | None = None,
        workspace: str | None = None,
        targets: list[SessionTarget] | None = None,
        target_summary: str | None = None,
        authorization_note: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: SessionStatus = SessionStatus.DRAFT,
    ) -> Session: ...

    def get_session(self, identifier: str) -> Session | None: ...
    def require_session(self, identifier: str) -> Session: ...

    def list_sessions(
        self,
        *,
        mode: SessionMode | None = None,
        status: SessionStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Session]: ...

    def get_latest_session(
        self,
        *,
        mode: SessionMode | None = None,
        status: SessionStatus | None = None,
        title_query: str | None = None,
    ) -> Session | None: ...

    def save_session(self, session: Session) -> Session: ...

    def update_session_status(
        self,
        identifier: str,
        status: SessionStatus,
        *,
        last_error: str | None = None,
    ) -> Session: ...

    def update_session_targets(
        self,
        identifier: str,
        *,
        targets: list[SessionTarget],
        target_summary: str | None = None,
    ) -> Session: ...

    def update_authorization_note(
        self,
        identifier: str,
        authorization_note: str | None,
    ) -> Session: ...
```

## Final Service Rules

### Create Rules

1. `title` must be non-empty.
2. `goal` must be non-empty.
3. `mode` must be valid.
4. `persistence_mode` defaults by `mode` if omitted.
5. `workspace` defaults to `settings.working_directory`.
6. `targets` defaults to `[]`.
7. `target_summary` is derived when omitted.

### Update Rules

1. Every successful update changes `updated_at`.
2. Entering `completed`, `failed`, or `cancelled` sets `closed_at` if not already set.
3. Entering `active` from `draft` or `paused` clears no historical fields unless explicitly requested.

### Lookup Rules

1. Product-facing flows should use public IDs and summaries when possible.
2. Internal flows may use internal IDs.
3. The service must support both through one identifier parameter.

## Validation Rules Frozen for Phase 1

The implementation must validate:

- required text fields
- enum membership
- legal state transitions
- non-empty target values
- valid target kinds

The implementation must not attempt to validate in Phase 1:

- scope policy correctness
- network reachability
- execution admissibility
- target authorization truth

Those belong to later layers.

## Final Legacy Boundary

### REWRITE REQUIRED

The new `SessionService` must not depend on:

- `TaskService.create_task(...)`
- `OperationService.create_operation(...)`

for top-level session creation.

### Legacy Classification

During Phase 1:

- `TaskService` is legacy
- `OperationService` is legacy
- `Task` is legacy
- `Operation` is legacy

They may remain in the repository temporarily, but they are no longer part of the target architecture contract.

### Replacement Meaning in Phase 1

In Phase 1, replacement means:

- replaced in domain model
- replaced in planning documents
- replaced in service contract direction

It does not yet mean:

- physically deleted everywhere
- removed from all temporary operator paths

### Allowed Temporary Migration Utilities

Allowed:

- one-off migration helpers
- internal classification tools
- read-only legacy inspection

Not allowed:

- routing new product flows through legacy top-level services
- promising compatibility as part of the new architecture

## Final Module Plan for Phase 1

New Phase 1 modules:

- `src/models/session.py`
- `src/app/session_service.py`
- `src/storage/repositories/sessions.py`

Expected touched files:

- `src/models/__init__.py`
- `src/app/__init__.py` if needed
- `src/storage/sqlite.py`
- relevant schema initialization files

Legacy files to freeze:

- `src/models/task.py`
- `src/models/operation.py`
- `src/app/task_service.py`
- `src/app/operation_service.py`

## Final Implementation Order

Phase 1 coding order is fixed as:

1. implement `src/models/session.py`
2. implement the sessions table and repository
3. implement `src/app/session_service.py`
4. add model, repository, and service tests
5. freeze legacy top-level services in docs and planning artifacts

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Test Plan for Phase 1

Recommended test files:

- `tests/test_session_model.py`
- `tests/test_session_repository.py`
- `tests/test_session_service.py`

Required test areas:

### Model

- default creation
- enum behavior
- JSON serialization helpers
- target summary derivation

### Repository

- create and read by internal ID
- create and read by public ID
- list ordering by `updated_at`
- JSON round-trip for targets and metadata

### Service

- default persistence mode selection
- legal and illegal transition handling
- latest session lookup
- target update behavior
- no dependency on legacy top-level services

## Phase 1 Ready-to-Implement Checklist

Phase 1 is now considered fully converged if the team accepts the following locked decisions:

- `SessionMode = normal | redteam`
- `SessionPersistenceMode = ephemeral | persistent`
- `SessionStatus = draft | active | paused | completed | failed | cancelled`
- `failed` is terminal in Phase 1
- public IDs use `S0001` format
- targets are stored as structured JSON on the session record
- repository lives in `src/storage/repositories/sessions.py`
- service lives in `src/app/session_service.py`
- new top-level flows must not call `TaskService` or `OperationService`

This checklist is now the Phase 1 baseline.
