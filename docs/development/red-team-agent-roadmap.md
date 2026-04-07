# Red-Team Agent Roadmap

## Purpose

This roadmap translates the red-team agent requirements into a phased implementation plan grounded in the current repository layout.

The plan assumes:

- the existing task runtime remains temporarily available as legacy behavior
- the new security-oriented runtime is introduced beside it
- correctness, scope control, and observability are more important than backward compatibility

## Implementation Status Snapshot

Current phase status based on the repository implementation:

- Phase 0: partially implemented
- Phase 1: implemented
- Phase 2: implemented
- Phase 3: implemented
- Phase 4: not yet implemented
- Phase 5: partially implemented
- Phase 6: partially implemented
- Phase 7: partially implemented
- Phase 8: partially implemented

## Current Repository Anchors

The current codebase already has strong extension points:

- `src/main.py`
- `src/cli/ui.py`
- `src/app/skill_service.py`
- `src/runtime/task_runner.py`
- `src/tools/executor.py`
- `src/tools/policy.py`
- `src/storage/`
- `src/models/`

The main architectural limitation today is that the runtime is still centered on:

- one shell
- one active task
- one foreground prompt loop
- one conversational checkpoint stream

The new runtime must shift toward:

- one operation
- many jobs
- typed tools
- structured evidence
- structured findings
- scope-aware orchestration

## Phase 0: Baseline Freeze and Runtime Partition

### Goal

Protect the current coding-agent runtime while creating space for a red-team-oriented runtime.

### Status

Partially implemented.

The current repository already provides:

- v1 `Task` / `Run` and v2 `Operation` / `Job` as parallel runtime families
- reserved `/operation` and `/job` CLI command groups

Still deferred:

- a dedicated v2 database file such as `.red-code/agent-v2.db`
- a full storage partition between legacy and v2 runtime state

### Work Items

- keep the current `Task` and `Run` runtime available as legacy behavior
- define a new runtime family for security operations
- introduce a separate SQLite database file for the new runtime
- define the new command namespace and CLI entry points

### Target Modules

- `src/main.py`
- `src/storage/sqlite.py`
- `src/runtime/`
- `src/cli/ui.py`

### Deliverables

- runtime-family split documented in code and docs
- new database path, such as `.red-code/agent-v2.db`
- reserved CLI command groups for the new runtime

## Phase 1: New Domain Model and Persistence

### Goal

Introduce the core entities required by the new runtime.

### Status

Implemented.

### Current Implementation Note

The current repository implements this phase in a same-database coexistence mode:

- new v2 tables live beside legacy `tasks`, `runs`, and `checkpoints`
- legacy runtime behavior remains unchanged
- minimal `/operation` and `/job` CLI inspection is included to satisfy the phase exit criteria
- a dedicated `agent-v2.db` split is deferred to a later partitioning pass

### Work Items

- add `Operation`
- add `ScopePolicy`
- add `Job`
- add `Evidence`
- add `Finding`
- add `MemoryEntry`
- add new repositories and schema initialization

### Proposed Module Additions

- `src/models/operation.py`
- `src/models/scope_policy.py`
- `src/models/job.py`
- `src/models/evidence.py`
- `src/models/finding.py`
- `src/models/memory.py`

- `src/storage/repositories/operations.py`
- `src/storage/repositories/scope_policies.py`
- `src/storage/repositories/jobs.py`
- `src/storage/repositories/evidence.py`
- `src/storage/repositories/findings.py`
- `src/storage/repositories/memory.py`

### Existing Modules to Leave Stable

- `src/models/task.py`
- `src/models/run.py`
- `src/storage/tasks.py`
- `src/storage/runs.py`
- `src/storage/checkpoints.py`

### Exit Criteria

- operations can be created and listed
- scope policies can be persisted and retrieved
- jobs can be created and queried

## Phase 2: Scope Policy Enforcement

### Goal

Upgrade safety from generic capability tiers to scope-aware admission control.

### Current Implementation Note

The current repository now implements this phase as a v2-only execution boundary:

- legacy task and chat flows still use the existing capability-tier `ToolExecutor`
- v2 red-team execution uses `ScopeValidator`, `OperationAdmissionService`, and `ScopedExecutionService`
- denial, confirmation, and execution audit facts are persisted in `operation_events`
- `bash` is not part of the v2 scoped execution path

### Work Items

- define target validation rules
- define allowed protocol and port checks
- define rate and concurrency limits
- enforce confirmation requirements from policy
- record detailed denial reasons

### Proposed Module Additions

- `src/models/operation_event.py`
- `src/storage/repositories/operation_events.py`
- `src/app/operation_event_service.py`
- `src/app/scoped_execution_service.py`
- `src/orchestration/admission.py`
- `src/orchestration/scope_validator.py`
- `src/orchestration/rate_limits.py`

### Exit Criteria

- no network-capable tool executes without scope validation
- out-of-scope requests are hard-blocked
- denial and confirmation events are persisted

### Status

Implemented for the v2 runtime family.

## Phase 3: Typed Security Tool Foundation

### Goal

Replace shell-heavy security execution with typed, auditable tools.

### Status

Implemented.

The repository now provides a dedicated typed security tool path beside the legacy LangChain tool registry. The general-purpose tool registry remains available for the v1 coding-agent workflow, while the v2 runtime can execute the typed MVP security tool set through scoped admission.

The legacy tool registry is still centered on general-purpose tools such as:

- `bash`
- `read_file`
- `write_file`
- `edit_file`
- `list_dir`
- `search`
- `web_fetch`
- `web_search`

### MVP Tool Set

- `dns_lookup`
- `http_probe`
- `tls_inspect`
- `banner_grab`
- `port_scan`

### Work Items

- define a shared tool contract
- implement structured argument validation
- normalize outputs
- emit evidence items
- emit finding candidates

### Proposed Module Additions

- `src/tools/contracts.py`
- `src/tools/security/dns_lookup.py`
- `src/tools/security/http_probe.py`
- `src/tools/security/tls_inspect.py`
- `src/tools/security/banner_grab.py`
- `src/tools/security/port_scan.py`

### Existing Modules to Refactor

- `src/tools/__init__.py`
- `src/tools/registry.py`
- `src/tools/executor.py`

### Notes

`bash` may remain in the repository, but it should not be the primary red-team execution path.

Phase 3 currently stops at structured result generation:

- typed tools emit evidence candidates
- typed tools emit finding candidates when appropriate
- confirmation-gated execution is re-admitted before execution so concurrency and rate limits cannot be bypassed
- `dns_lookup` validates both the queried logical name and the real resolver egress target
- `http_probe` records only the first HTTP response and does not auto-follow redirects
- automatic persistence of those candidates remains deferred to Phase 5

### Exit Criteria

- typed security tools are callable through the unified executor
- tool results are structured and inspectable
- shell is no longer required for the main MVP workflows

## Phase 4: Scheduler and Worker Runtime

### Goal

Move from one prompt equals one foreground run to a background-capable job runtime.

### Status

Not yet implemented.

The repository currently persists `Job` records and job logs, but it does not yet provide the scheduler, worker, lease, heartbeat, timeout, cancellation, or retry orchestration described in this phase.

### Work Items

- add job queueing
- add worker leasing
- add heartbeat tracking
- add timeout handling
- add cancellation
- add retry policy

### Proposed Module Additions

- `src/orchestration/job_service.py`
- `src/orchestration/scheduler.py`
- `src/runtime/worker.py`
- `src/runtime/leases.py`
- `src/runtime/timeouts.py`

### Existing Modules to Decouple

- `src/runtime/task_runner.py`

The legacy task runner should not remain the center of security execution once job orchestration exists.

### Exit Criteria

- multiple jobs can run independently
- worker crashes do not silently lose job state
- timeouts and cancellations produce explicit terminal job states

## Phase 5: Evidence and Findings Pipeline

### Goal

Promote execution output into durable proof and analyst-friendly conclusions.

### Status

Partially implemented.

The repository already provides:

- `Evidence`, `Finding`, and `MemoryEntry` models
- SQLite-backed repositories and services for those entities

Still missing from this phase:

- automatic evidence creation from successful typed jobs
- automatic finding candidate generation
- managed evidence artifact storage and export modules

### Work Items

- persist evidence metadata
- write evidence artifacts to managed storage
- persist finding candidates
- support finding confirmation and dismissal
- support evidence-to-finding traceability

### Proposed Module Additions

- `src/app/evidence_service.py`
- `src/app/finding_service.py`
- `src/reporting/findings_summary.py`
- `src/reporting/evidence_export.py`

### Filesystem Layout

- `.red-code/operations/<operation_id>/evidence/`
- `.red-code/operations/<operation_id>/exports/`

### Exit Criteria

- successful jobs produce evidence
- findings can be reviewed without transcript replay
- exports can be generated from structured data

## Phase 6: Skill System Evolution

### Goal

Keep skills as workflow specializers while moving security control into runtime code.

### Status

Partially implemented.

The repository already:

- preserves prompt overlays and tool narrowing
- parses extension fields such as `model`, `effort`, `shell`, `user-invocable`, and `disable-model-invocation`

Still missing from this phase:

- operational use of those parsed extension fields in the runtime
- bounded job-template generation from skills
- dedicated security workflow skills built around the v2 runtime

### Work Items

- preserve prompt overlays and tool narrowing
- add security workflow skills such as `surface-recon` and `web-enum`
- make `model`, `effort`, `shell`, `user-invocable`, and `disable-model-invocation` affect runtime behavior
- allow skills to generate bounded job templates instead of only changing prompts

### Primary Refactor Targets

- `src/app/skill_service.py`
- `src/skills/loader.py`
- `src/models/skill.py`
- `src/skills/`

### Exit Criteria

- skills influence planning and tool visibility
- skills do not bypass scope policy
- currently parsed extension fields are operationally meaningful

## Phase 7: CLI and Dashboard

### Goal

Expose the new runtime cleanly to the operator.

### Status

Partially implemented.

The repository currently provides:

- `/operation create|list|show`
- `/job create|list|show`
- help text and Rich presentation for those minimal v2 inspection flows

Still missing from this phase:

- `/finding`
- `/evidence`
- `/dashboard`
- v2 lifecycle commands such as pause, resume, and cancel

### Work Items

- add operation commands
- add job commands
- add finding commands
- add evidence commands
- add dashboard view

### Command Groups

- `/operation create|list|show|pause|resume`
- `/job list|show|cancel`
- `/finding list|show|confirm|dismiss`
- `/evidence list|show`
- `/dashboard`

### Primary Refactor Targets

- `src/main.py`
- `src/cli/ui.py`

### Exit Criteria

- operators can inspect live and historical operation state
- blocked actions and failures are easy to identify
- the CLI no longer depends on task-only concepts for security workflows

## Phase 8: Structured Memory and Planner Runtime

### Goal

Support higher-level orchestration without reverting to transcript-heavy control.

### Status

Partially implemented.

The repository already persists structured memory entries, but it does not yet provide planner runtime orchestration, planner-generated job proposals, or planner context assembly from evidence and open findings.

### Work Items

- add structured memory entries
- build planner context from memory, evidence, and open findings
- allow planners to create job proposals
- keep planners unable to widen scope or bypass typed tools

### Proposed Module Additions

- `src/orchestration/planner_runtime.py`
- `src/app/memory_service.py`

### Exit Criteria

- planners can propose next steps from stored facts
- resumed operations do not require transcript replay to recover context

## Recommended Delivery Order

Recommended implementation order:

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 7
8. Phase 6
9. Phase 8

Rationale:

- scope control must arrive before meaningful security execution
- typed tools must arrive before broad security skills
- evidence and findings must exist before advanced planning becomes worthwhile

## Testing Strategy by Phase

### Early Phases

- schema initialization tests
- repository round-trip tests
- scope validation tests
- policy denial tests

### Mid Phases

- typed tool contract tests
- evidence persistence tests
- finding generation tests
- scheduler lease and timeout tests

### Late Phases

- CLI inspection tests
- planner proposal tests
- end-to-end operation tests

## Migration Notes

- keep the old task runtime available during development
- do not force `Operation` to masquerade as `Task`
- do not stretch checkpoint transcripts into the primary memory model for the new runtime
- prefer a clean v2 runtime family over deep compatibility layers

## First Practical Milestone

The first milestone should deliver:

- `Operation`
- `ScopePolicy`
- `Job`
- at least three typed security tools
- evidence persistence
- finding persistence
- CLI inspection for operation and job state

Current milestone status:

- delivered: `Operation`
- delivered: `ScopePolicy`
- delivered: `Job`
- delivered: at least three typed security tools
- delivered: evidence persistence
- delivered: finding persistence
- delivered: CLI inspection for operation and job state

That milestone is the point where `red-code` starts behaving like a real local security-operation agent rather than a generic coding agent with security-themed prompts.
