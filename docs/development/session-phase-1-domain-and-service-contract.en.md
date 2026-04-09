# Phase 1 Domain and Service Contract Draft

## Purpose

This document defines the proposed **Phase 1 domain model, persistence contract, and service contract** for the new `session` top-level runtime model.

It exists to remove ambiguity before implementation begins. The goal is to make the first coding phase concrete enough that:

- naming decisions are stable
- field definitions are explicit
- repository boundaries are clear
- `SessionService` can be implemented without leaning on `TaskService` or `OperationService`

This document should be read together with:

- [Phase 1 Implementation Checklist](D:\Project\Python\Agent\docs\development\session-phase-1-implementation-checklist.en.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)

## Design Constraints

### 1. `session` Is a Real New Model

`session` must not be a cosmetic alias for either `task` or `operation`.

### 2. One Product-Facing Top-Level Entity

The new runtime must have a single top-level user-facing work unit.

### 3. Internal Reuse Is Allowed

Lower-level internals such as jobs, findings, scope validation, and typed tools may remain reusable implementation details.

### 4. No Old-Model Compatibility Contract

The new public runtime contract must not promise long-term compatibility with:

- `task`
- `operation`
- their current service interfaces

## Proposed Domain Model

## Session

Recommended file:

- `src/models/session.py`

### Proposed Fields

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
  target_summary: str | None
  authorization_note: str | None
  created_at: str
  updated_at: str
  closed_at: str | None
  last_error: str | None
  metadata: dict[str, Any]
```

### Field Rationale

#### `id`

Internal stable identifier.

Recommended format:

- UUID string

#### `public_id`

Human-usable label for CLI and future UI surfaces.

Recommended format:

- `S0001`, `S0002`, ...

This is optional at the storage layer only if the repository is responsible for assigning it during create.

#### `title`

Short human-readable session name.

Examples:

- `Example Recon`
- `Internal API Review`
- `Temporary TLS Check`

#### `goal`

The plain-language purpose of the session.

Examples:

- `Assess the exposed surface of example.com`
- `Run a temporary TLS inspection for the target host`

#### `mode`

Controls the high-level product behavior.

Recommended enum:

- `normal`
- `redteam`

#### `persistence_mode`

Separates runtime mode from persistence intent.

Recommended enum:

- `ephemeral`
- `persistent`

This allows:

- `normal` + `ephemeral`
- `normal` + `persistent` if needed later
- `redteam` + `persistent`

The initial product default should still be:

- `normal` -> ephemeral
- `redteam` -> persistent

#### `workspace`

The working directory or base workspace path.

This should remain explicit because it matters for file tools and future UI behavior.

#### `status`

Shared lifecycle state across both session modes.

#### `target_summary`

A short human-readable summary such as:

- `example.com`
- `example.com, 93.184.216.34`
- `staging API and related hosts`

This is not the authoritative target store. It exists for UX and list views.

#### `authorization_note`

Short free-form text describing authorization context, engagement note, or operator intent.

This is intentionally lightweight and does not replace future structured authorization metadata if needed.

#### `created_at`, `updated_at`, `closed_at`

Standard lifecycle timestamps.

#### `last_error`

Most recent session-level error summary.

#### `metadata`

Reserved extensibility field for non-core session attributes.

It should not be used to avoid proper schema design for known core fields.

## SessionTarget

Recommended file:

- either keep embedded in `src/models/session.py`
- or create `src/models/session_target.py` only if it significantly improves clarity

### Recommendation

For Phase 1, prefer embedding target records inside `Session.metadata` **only if** a proper target list field is also defined in the model contract.

A better Phase 1 direction is:

```text
SessionTarget
  kind: SessionTargetKind
  value: str
  note: str | None
```

Recommended target kinds:

- `domain`
- `host`
- `ip`
- `cidr`
- `url`

### Session Target Storage Decision

For Phase 1, prefer **embedded structured JSON storage** over a fully normalized relational target table.

Reason:

- the target model is still evolving
- Phase 1 needs speed and clarity more than relational flexibility
- a normalized target table can be added later if query patterns demand it

Recommended `Session` model addition:

```text
targets: list[SessionTarget]
```

## Proposed Enums

### SessionMode

```text
normal
redteam
```

### SessionPersistenceMode

```text
ephemeral
persistent
```

### SessionStatus

Recommended initial statuses:

```text
draft
active
paused
completed
failed
cancelled
```

### Why This Status Set

It works across both modes without inheriting the old split directly:

- `draft` covers not-yet-started or partially initialized work
- `active` covers the currently running or engaged state
- `paused` covers deliberate operator or system pause
- `completed` covers successful closure
- `failed` covers unrecoverable or terminal failure
- `cancelled` covers deliberate stop

This avoids carrying over:

- task-only semantics such as `pending`
- operation-only semantics such as `ready` and `blocked`

Those concepts can remain lower-level execution details later if still useful.

## Proposed State Transitions

Allowed state transitions should be explicit.

```text
draft -> active
draft -> cancelled

active -> paused
active -> completed
active -> failed
active -> cancelled

paused -> active
paused -> cancelled
paused -> failed

failed -> active        (optional, only if restart semantics are supported)
failed -> cancelled     (optional)

completed -> [terminal]
cancelled -> [terminal]
```

### Recommendation

For Phase 1:

- allow `failed -> active` only if the service explicitly supports resuming or retrying a session
- otherwise treat `failed` as terminal and restart by creating a new session or later by explicit recovery flow

## Persistence Contract

## Recommended Repository File

- `src/storage/repositories/sessions.py`

## Recommended Table

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

## Recommended Indexes

```sql
CREATE INDEX idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX idx_sessions_mode ON sessions(mode);
CREATE INDEX idx_sessions_status ON sessions(status);
```

Optional later indexes:

- title search support
- workspace filtering

## Serialization Contract

The repository should serialize:

- `targets` into `targets_json`
- `metadata` into `metadata`

using UTF-8 JSON with `ensure_ascii=False`.

## Repository Interface Draft

Recommended responsibilities:

- create
- get by internal ID
- get by public ID
- get by either identifier
- list
- update

### Proposed Interface

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
    def next_public_id(self) -> str: ...
```

### Important Notes

#### `get(identifier)`

This should accept:

- internal ID
- public ID

This preserves user-friendly lookup without making public IDs mandatory in every internal call.

#### `next_public_id()`

If the repository owns public ID assignment, make it explicit.

Alternative:

- assign public IDs inside `create()`

Either choice is acceptable, but the contract must be clear and consistent.

## Service Contract

## Recommended File

- `src/app/session_service.py`

## Service Responsibilities

`SessionService` should own the top-level session lifecycle.

It should not yet own:

- job orchestration
- scope validation
- tool execution
- evidence generation

Those belong to later phases or lower-level services.

## Proposed Service Methods

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
        closed_at: str | None = None,
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

## Service Rules

### Create Rules

1. `title` and `goal` are required.
2. `mode` is required.
3. `persistence_mode` defaults by `mode` if omitted.
4. `workspace` defaults to `settings.working_directory`.
5. `targets` defaults to an empty list.
6. `target_summary` may be auto-derived from targets if not supplied.

### Status Rules

1. The service must validate legal status transitions.
2. `closed_at` should be set when entering terminal states if not already set.
3. `updated_at` must change on every persisted update.

### Retrieval Rules

1. User-facing code should prefer public IDs and summaries.
2. Internal code may use internal IDs.
3. The service should support both through one lookup method.

## Validation Rules

The Phase 1 implementation should validate at least:

- `title` is non-empty
- `goal` is non-empty
- `mode` is valid
- `persistence_mode` is valid
- `status` is valid
- `targets` contain valid kinds and non-empty values

It should not yet validate:

- deep scope compatibility
- network reachability
- target authorization correctness

Those belong to later execution and policy layers.

## Derived Helpers

The service or model may expose helpers such as:

- `is_redteam_session`
- `is_persistent`
- `is_terminal`
- `derive_target_summary(targets)`

These are encouraged if they reduce duplicated logic without bloating the domain model.

## Error Contract

### Repository Errors

Recommended behavior:

- storage-level failures raise repository-specific or persistence exceptions

### Service Errors

Recommended behavior:

- missing session -> `ValueError` or a domain-specific not-found error
- invalid status transition -> `ValueError` or a domain-specific transition error
- invalid create input -> `ValueError`

The exact exception hierarchy may evolve later, but the Phase 1 implementation should at least be consistent.

## Legacy Boundary Contract

### REWRITE REQUIRED

The new `SessionService` must not call:

- `TaskService.create_task(...)`
- `OperationService.create_operation(...)`

to create its top-level object.

If migration helpers are needed, they must be kept separate from the new runtime contract.

### Allowed Temporary Boundary

Temporary migration code may:

- read legacy data
- classify legacy records
- support one-off migration tooling

It must not:

- define the new public runtime behavior
- be required by new session creation paths

## Suggested Module Map

Recommended Phase 1 module layout:

```text
src/
  models/
    session.py
  app/
    session_service.py
  storage/
    repositories/
      sessions.py
```

Optional support:

```text
src/
  app/
    session_migration_service.py
```

## Implementation Order

Use this order during coding.

### Step 1. Finalize the Model Contract

Before any storage implementation:

- finalize fields
- finalize enums
- finalize state transitions

### Step 2. Implement `src/models/session.py`

Add:

- enums
- dataclass
- create constructor
- serialization helpers
- update helpers

### Step 3. Implement the Session Repository

Add:

- schema
- create/get/list/update methods
- public ID generation logic

### Step 4. Implement `SessionService`

Add:

- creation logic
- retrieval logic
- transition validation
- target update methods

### Step 5. Add Tests

Add:

- model tests
- repository tests
- service tests

### Step 6. Freeze Legacy Top-Level Services

After the new session path exists:

- stop evolving task and operation as target-state APIs
- update docs to classify them as legacy

## Test Contract Draft

The following test files are recommended.

- `tests/test_session_model.py`
- `tests/test_session_repository.py`
- `tests/test_session_service.py`

### `test_session_model.py`

Recommended checks:

- create default values
- enum serialization
- target summary handling
- status helper behavior

### `test_session_repository.py`

Recommended checks:

- create and get by internal ID
- get by public ID
- update persistence
- list ordering by `updated_at`
- targets JSON round-trip

### `test_session_service.py`

Recommended checks:

- default persistence mode by session mode
- invalid transition rejection
- latest-session retrieval
- target update behavior
- no dependency on legacy top-level services

## Open Decisions to Resolve Before Coding

The following questions should be answered before implementation starts.

### 1. Public ID Format

Recommendation:

- use `S0001` style IDs

### 2. Target Storage

Recommendation:

- store targets as structured JSON in Phase 1

### 3. Terminal State Semantics

Recommendation:

- treat `completed` and `cancelled` as terminal
- decide whether `failed` can be resumed before coding

### 4. Persistence Defaults

Recommendation:

- `normal` -> `ephemeral`
- `redteam` -> `persistent`

## Exit Criteria

Phase 1 domain and service design is ready for implementation when:

1. The `Session` fields are fixed.
2. The enum set is fixed.
3. The state transitions are fixed.
4. The repository interface is fixed.
5. The `SessionService` method set is fixed.
6. The legacy boundary rule is explicit.

At that point, implementation can begin without re-litigating the product model.
