# Phase 1 Implementation Checklist: Session Domain Reset

## Purpose

This document breaks down **Phase 1: Session Domain Reset** from the session refactor plan into implementation-ready engineering tasks.

It is intended to answer:

- what must be built first
- which modules should be introduced
- which existing modules must be rewritten
- which legacy paths must be removed
- in what order the work should be performed

This checklist assumes the target direction is already fixed by:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)

## Phase Goal

Introduce `session` as the only top-level user-facing work unit and remove the old `task` / `operation` split from the target product model.

## Scope of Phase 1

This phase covers:

- domain model definition
- persistence model design
- service interface design
- naming reset in docs and product contracts
- migration boundaries for legacy concepts

This phase does **not** yet require:

- the full natural-language controller flow
- the full foreground execution loop
- the full skill/module runtime rewrite
- the full storage split into `memory/`, `artifacts/`, `findings/`, and `reports/`

## Non-Goals

Do not do the following in Phase 1:

- keep both `task` and `operation` as permanent product-facing concepts
- add another compatibility abstraction on top of `task` and `operation`
- rename old objects cosmetically without resetting the model
- redesign all CLI flows before the session domain exists

## Rewrite Policy

### REWRITE REQUIRED

Phase 1 is a **domain reset**, not a compatibility pass.

The implementation should prefer:

- introducing a clean `session` model
- explicitly marking legacy modules as deprecated or scheduled for removal
- isolating old paths from new product contracts

The implementation should avoid:

- adapting `task` until it "looks enough like" `session`
- adapting `operation` until it "looks enough like" `session`
- preserving both and postponing the real merge indefinitely

## Target Outcomes

By the end of Phase 1:

1. `session` exists as the top-level product domain model.
2. There is a defined `SessionService` contract.
3. There is a defined persistence contract for sessions.
4. Product-facing docs no longer treat `task` and `operation` as the future top-level UX.
5. The codebase has a clear module-level migration boundary between:
   - retained internals
   - rewritten top-level flows
   - legacy paths pending deletion

## Module Strategy

## Modules to Introduce

These modules should be added in Phase 1.

### Domain Model

- `src/models/session.py`

Recommended responsibilities:

- define the `Session` entity
- define the session type or mode
- define the session status model
- serialize and deserialize session data

### Application Service

- `src/app/session_service.py`

Recommended responsibilities:

- create session
- load session
- list sessions
- update session status
- update target metadata
- expose user-friendly session labels

### Repository

One of the following approaches should be chosen:

- `src/storage/repositories/sessions.py`
- or `src/storage/sessions.py`

Preferred direction:

- keep new session persistence inside the newer repository-style layout if possible

### Migration Support

Optional internal helper modules:

- `src/app/session_migration_service.py`
- `src/storage/migrations/` additions if needed

These should be temporary and explicitly internal.

## Existing Modules to Rewrite

These modules are Phase 1 rewrite targets.

### REWRITE REQUIRED: `src/models/task.py`

Decision:

- do not evolve this into the permanent session model

Action:

- keep only as a legacy artifact during the migration window
- stop treating it as the future top-level abstraction

### REWRITE REQUIRED: `src/models/operation.py`

Decision:

- do not keep this as the permanent top-level user model

Action:

- preserve only as a legacy/internal model during migration if needed
- do not allow new product contracts to depend on it

### REWRITE REQUIRED: `src/app/task_service.py`

Decision:

- this is not the future top-level service

Action:

- stop extending it for new product work
- plan replacement by `SessionService`

### REWRITE REQUIRED: `src/app/operation_service.py`

Decision:

- this is not the future top-level service

Action:

- stop extending it as the permanent product entry point
- extract reusable lower-level policy logic later if needed

### REWRITE REQUIRED: Top-Level Documentation Contracts

Affected files:

- `docs/README.md`
- `docs/architecture/architecture.md`
- `docs/architecture/task-runtime.md`
- `docs/development/engineering-development-plan.en.md`
- `docs/development/red-team-agent-roadmap.md`

Action:

- remove any implication that the future product is built around both `task` and `operation`

## Existing Modules to Keep as Internal Reuse Candidates

These are not Phase 1 rewrite targets, but Phase 1 should classify them as reusable internals for later phases.

- `src/orchestration/scope_validator.py`
- `src/app/scoped_execution_service.py`
- `src/app/security_tool_execution_service.py`
- `src/runtime/worker.py`
- `src/orchestration/scheduler.py`
- `src/orchestration/job_service.py`
- `src/tools/security/`
- `src/app/evidence_service.py`
- `src/app/finding_service.py`

Phase 1 should not heavily modify these modules unless needed for interface isolation.

## File-Level Checklist

## 1. Add the New Session Domain Model

Files:

- `src/models/session.py`
- `src/models/__init__.py`

Checklist:

- define `Session`
- define `SessionMode`
- define `SessionStatus`
- define serialization helpers
- define target metadata shape
- define user-facing label helper fields

Completion check:

- a session can be represented without any reference to `task` or `operation`

## 2. Add the New Session Persistence Layer

Files:

- `src/storage/repositories/sessions.py` or `src/storage/sessions.py`
- `src/storage/sqlite.py`
- new schema definitions or migrations

Checklist:

- define the sessions table or equivalent persistence structure
- define create/get/list/update operations
- define indexing needed for recent-session retrieval
- define a migration path for new storage initialization

Completion check:

- sessions can be created, loaded, and listed independently of legacy top-level stores

## 3. Add the New Session Service

Files:

- `src/app/session_service.py`

Checklist:

- create session
- get session
- list sessions
- update session status
- update targets
- expose human-friendly summaries

Completion check:

- application logic can use sessions without calling `TaskService` or `OperationService`

## 4. Update Public Domain Exports

Files:

- `src/models/__init__.py`
- `src/app/__init__.py` if needed

Checklist:

- export session-related models cleanly
- avoid accidental import loops
- ensure new imports do not force legacy top-level imports

Completion check:

- new session modules are importable as first-class runtime components

## 5. Mark Legacy Top-Level Paths as Legacy

Files:

- `src/models/task.py`
- `src/models/operation.py`
- `src/app/task_service.py`
- `src/app/operation_service.py`
- related docs

Checklist:

- mark them in docs or comments as legacy during migration
- stop adding new target-architecture work to them
- isolate them from new product-facing contracts

Completion check:

- the team can clearly tell which top-level abstractions are legacy and which are target-state

## 6. Align Documentation with the New Top-Level Model

Files:

- `docs/README.md`
- `docs/architecture/architecture.md`
- `docs/development/engineering-development-plan.en.md`
- `docs/development/red-team-agent-roadmap.md`

Checklist:

- update the roadmap language to point toward `session`
- remove future-facing wording that assumes the permanent coexistence of `task` and `operation`
- reference the new session phase documents

Completion check:

- no current planning document describes `task` plus `operation` as the intended end-state product model

## Data Model Checklist

The new `Session` model should answer these questions explicitly.

### Identity

- What is the internal ID type?
- Is there a human-friendly public ID?
- Is the session title user-editable?

### Mode

- Is this `normal` or `redteam`?
- Is persistence implied by mode or separately configurable?

### Targets

- Can the session hold domains, IPs, CIDRs, and free-form notes?
- Is target storage normalized or embedded?

### Status

- What are the valid statuses?
- Which statuses are shared across `normal` and `redteam`?
- Which transitions are allowed?

### Metadata

- How are created/updated timestamps tracked?
- How is authorization context represented?
- How is a human-readable summary produced?

## Suggested Initial Session Statuses

The exact list may evolve, but the Phase 1 implementation should define an initial status set.

Recommended candidate statuses:

- `draft`
- `active`
- `paused`
- `completed`
- `failed`
- `cancelled`

If a different set is chosen, it should still:

- work for both `normal` and `redteam`
- avoid copying the old task and operation status split blindly

## Migration Sequence

Work should be performed in this order.

### Step 1. Define the Session Model on Paper

Before coding:

- finalize fields
- finalize statuses
- finalize session mode semantics
- finalize persistence assumptions

Reason:

- service and storage design should not drift from an unfinished domain model

### Step 2. Add the Session Model and Persistence

Implement:

- `src/models/session.py`
- session repository
- schema changes

Reason:

- the service layer should be built on real storage contracts

### Step 3. Add the Session Service

Implement:

- `src/app/session_service.py`

Reason:

- this becomes the future entry point for higher-level runtime flows

### Step 4. Freeze Legacy Top-Level Services

Apply:

- documentation warnings
- explicit "legacy" classification
- no new top-level product work in `TaskService` and `OperationService`

Reason:

- prevent backsliding during later phases

### Step 5. Update Planning Documents

Update:

- roadmap docs
- architecture docs
- phase planning docs

Reason:

- implementation should not fight stale documentation

## Deletion and Deprecation Checklist

Phase 1 should not necessarily delete all old code immediately, but it must define the deletion path.

### Mark for Eventual Removal

- `/task` as the primary product workflow
- `/operation` as the primary product workflow
- `TaskService` as the primary top-level service
- `OperationService` as the primary top-level service
- any docs presenting both top-level models as the permanent architecture

### Keep Temporarily, but Internal Only

- worker runtime
- job orchestration
- typed security tools
- evidence and finding services

## Testing Checklist

## Unit Tests

Add or update tests for:

- session model creation
- session status validation
- session serialization
- session persistence round-trip
- session service CRUD flows

## Integration Tests

Add or update tests for:

- session service with SQLite-backed storage
- session list ordering
- session target metadata persistence

## Regression Protection

Add tests that ensure:

- new session flows do not require `task`
- new session flows do not require `operation`
- session service can exist without importing legacy top-level services

## Phase 1 Exit Review

Phase 1 should be considered complete only if all questions below can be answered with "yes".

1. Does the codebase now have a real `session` domain model?
2. Is there a real persistence path for sessions?
3. Is there a real `SessionService` contract?
4. Are `task` and `operation` clearly classified as legacy for product-facing design?
5. Can the next phase build the controller on top of `session` instead of legacy top-level services?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 1 are:

- `src/models/session.py`
- session persistence module
- `src/app/session_service.py`
- updated docs reflecting `session` as the target top-level concept
- legacy classification notes for `task` and `operation`

If any of these are missing, the architecture reset is not yet real.
