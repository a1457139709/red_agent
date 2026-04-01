# Red-Team Agent Implementation Plan V2

## Purpose

This document translates the V2 architecture into an execution plan that is concrete enough for implementation work.

It assumes:

- the V2 runtime is a replacement architecture
- compatibility with the current task runtime is not a goal
- code quality and safety are more important than preserving old interfaces

Primary references:

- [red-team-agent-architecture-v2.md](/D:/Project/Python/Agent/docs/red-team-agent-architecture-v2.md)
- [red-team-agent-schema-v2.md](/D:/Project/Python/Agent/docs/red-team-agent-schema-v2.md)

## Delivery Strategy

Build the V2 runtime as a separate vertical slice.

Recommended sequence:

1. new schema and repositories
2. operation and policy services
3. typed security tool contract
4. scheduler and worker runtime
5. planner runtime and memory
6. CLI dashboards and reporting
7. legacy removal

Do not begin with prompt work.
Do not begin with UI polish.

## Workstreams

The work should be organized into six streams:

- domain and storage
- typed tools
- scheduler and workers
- planner and memory
- command and dashboard
- testing and hardening

## Phase 1: Domain and Storage Reset

### Goal

Create the new runtime backbone with no dependency on the old task model.

### Deliverables

- V2 database bootstrap
- new repositories
- operation artifact directory management
- domain models and enums

### Module targets

- `src/storage/sqlite.py`
- `src/storage/repositories/operations.py`
- `src/storage/repositories/scope_policies.py`
- `src/storage/repositories/planner_runs.py`
- `src/storage/repositories/jobs.py`
- `src/storage/repositories/job_dependencies.py`
- `src/storage/repositories/evidence.py`
- `src/storage/repositories/findings.py`
- `src/storage/repositories/memory.py`
- `src/storage/repositories/workers.py`
- `src/domain/operations/`
- `src/domain/scope/`
- `src/domain/jobs/`
- `src/domain/findings/`
- `src/domain/evidence/`
- `src/domain/memory/`

### Concrete tasks

1. Add a new V2 database initializer for `.red-code/agent-v2.db`.
2. Add `app_metadata` bootstrap and schema validation.
3. Implement repository classes for all V2 core tables.
4. Implement explicit enum validation in domain models rather than scattering string checks.
5. Add operation artifact path helpers rooted at `.red-code/operations/<operation_id>/`.
6. Add service-level deletion helpers for managed artifact cleanup.

### Exit criteria

- a fresh V2 workspace initializes successfully
- operations can be created, updated, listed, and deleted
- scope policies can be attached and validated
- jobs can be inserted and queried
- no old task repository is imported anywhere in V2 code

## Phase 2: Operation and Scope Services

### Goal

Make scope policy a hard runtime requirement instead of a prompt instruction.

### Deliverables

- `OperationService`
- `ScopePolicyService`
- scope validation library
- operation lifecycle rules

### Module targets

- `src/domain/operations/service.py`
- `src/domain/scope/service.py`
- `src/domain/scope/validators.py`
- `src/domain/scope/types.py`

### Concrete tasks

1. Define operation lifecycle transitions.
2. Reject transition to `ready` unless a valid scope policy exists.
3. Implement target validators for:
   - host
   - domain
   - CIDR
   - port
   - protocol
4. Implement a single reusable `ScopeDecision` result type.
5. Add scope admission checks that can be reused by planners, scheduler, and tools.

### Exit criteria

- out-of-scope targets are denied before job admission
- operations cannot run without a policy
- scope validation rules are centralized and test-covered

## Phase 3: Typed Security Tool Foundation

### Goal

Replace shell-first security execution with typed tools.

### Deliverables

- common tool contract
- tool registry
- initial production tools
- normalized result types

### Initial tool set

- `dns_lookup`
- `http_probe`
- `port_scan`

Defer the rest until the contract is stable.

### Module targets

- `src/tools/contracts.py`
- `src/tools/registry.py`
- `src/tools/security/dns_lookup.py`
- `src/tools/security/http_probe.py`
- `src/tools/security/port_scan.py`
- `src/domain/evidence/materializer.py`
- `src/domain/findings/candidates.py`

### Concrete tasks

1. Define typed request and response objects for all security tools.
2. Define a shared validation path:
   - parse args
   - validate target
   - validate scope
   - apply execution limits
3. Define a normalized output format with:
   - summary
   - structured result
   - evidence items
   - finding candidates
   - metrics
4. Forbid direct use of generic `bash` in V2 red-team paths.
5. Add evidence materialization helpers that store artifacts under operation directories.

### Exit criteria

- tools can run without using the old generic executor path
- tool outputs are normalized and persisted
- out-of-scope requests are rejected consistently

## Phase 4: Scheduler and Worker Runtime

### Goal

Introduce real concurrent execution with reliable job leasing and recovery.

### Deliverables

- scheduler
- worker process runtime
- lease management
- timeout and cancellation support
- retry policy

### Module targets

- `src/orchestration/scheduler.py`
- `src/orchestration/admission.py`
- `src/orchestration/worker_manager.py`
- `src/runtime/worker.py`
- `src/runtime/leases.py`
- `src/runtime/timeouts.py`

### Concrete tasks

1. Implement job admission rules:
   - scope passed
   - dependencies satisfied
   - operation status allows execution
2. Implement queue polling ordered by:
   - priority
   - created time
3. Implement a lease model with explicit expiration.
4. Add worker heartbeats and stale-worker recovery.
5. Implement terminal job completion writeback.
6. Implement safe cancellation semantics.
7. Implement retry classification:
   - retryable
   - terminal
   - policy-blocked

### Exit criteria

- multiple workers can execute jobs concurrently
- jobs are not double-claimed
- stale leases are recovered safely
- worker crash leaves the system recoverable

## Phase 5: Findings and Evidence Pipeline

### Goal

Make proof and conclusions first-class outputs.

### Deliverables

- evidence materialization pipeline
- finding candidate promotion flow
- dedupe and merge rules
- exportable summaries

### Module targets

- `src/domain/evidence/service.py`
- `src/domain/evidence/materializer.py`
- `src/domain/findings/service.py`
- `src/domain/findings/dedupe.py`
- `src/reporting/findings_summary.py`
- `src/reporting/evidence_export.py`

### Concrete tasks

1. Define evidence item schemas for each tool.
2. Materialize artifacts atomically when possible.
3. Add digest validation and byte-size capture.
4. Define finding candidate schema.
5. Implement finding dedupe with stable dedupe keys.
6. Add operation-level findings summary generation.

### Exit criteria

- every successful tool run can emit durable evidence
- findings can be reviewed independently of raw logs
- duplicate findings do not spam the operation view

## Phase 6: Planner Runtime and Memory

### Goal

Reintroduce agent intelligence on top of a safe execution substrate.

### Deliverables

- planner runtime
- planner-run persistence
- memory retrieval and write rules
- bounded sub-agent delegation

### Module targets

- `src/orchestration/planner_runtime.py`
- `src/domain/planners/service.py`
- `src/domain/memory/service.py`
- `src/domain/memory/retrieval.py`
- `src/domain/memory/ingestion.py`

### Concrete tasks

1. Define planner input assembly from:
   - scope policy
   - memory profile
   - relevant memory entries
   - recent evidence summaries
   - open findings
2. Define planner outputs:
   - job proposals
   - finding updates
   - memory write proposals
3. Add a proposal validator between planner and scheduler.
4. Implement memory ingestion rules that reject noisy transcript fragments.
5. Implement bounded sub-agent roles with explicit allowed tool categories.

### Exit criteria

- planners can create valid jobs without touching raw execution paths
- planners cannot bypass scope policy
- memory remains concise and reusable

## Phase 7: Commands, Dashboard, and Reporting UX

### Goal

Make concurrent operation state observable and operable from the CLI.

### Deliverables

- new command group
- dashboard
- job inspection
- findings and evidence views

### Module targets

- `src/command/cli.py`
- `src/command/operation_commands.py`
- `src/command/job_commands.py`
- `src/command/dashboard.py`

### Concrete tasks

1. Add operation management commands.
2. Add job list, show, and cancel commands.
3. Add a live dashboard view with:
   - active jobs
   - operation summary
   - recent findings
   - recent evidence
4. Add findings and evidence inspection commands.
5. Keep the command surface V2-only for new red-team workflows.

### Exit criteria

- operators can monitor concurrent work without reading the database
- findings and evidence are inspectable from the CLI

## Phase 8: Legacy Removal

### Goal

Remove the old runtime from the critical path after V2 is usable.

### Concrete tasks

1. Mark the old task runtime as legacy.
2. Remove legacy commands from the default help surface.
3. Delete V2-forbidden red-team code paths that still depend on generic `bash`.
4. Remove compatibility notes from docs after cutover.
5. Delete old runtime modules once V2 covers core operation flows.

### Exit criteria

- V2 is the default runtime for red-team workflows
- no new feature work lands in the legacy task runtime

## Cross-Cutting Rules

### Rule 1: No mixed abstractions

Do not create hybrid types such as:

- "task operation"
- "run job"
- "checkpoint-backed evidence"

If the concept is new, name it directly and use it consistently.

### Rule 2: No shell as the fallback design

Temporary shell wrappers may exist behind typed tools during bootstrapping, but shell execution must never be the public contract of a V2 security tool.

### Rule 3: No prompt-only safety

All critical boundaries must be enforced in code.

### Rule 4: No transcript-heavy memory

Planner memory must store facts, evidence summaries, and rules rather than replaying long conversation logs.

### Rule 5: No long-lived compatibility shims

Short-lived development partitions are acceptable.
Permanent adapters are not.

## Testing Plan

## 1. Repository tests

Validate:

- table bootstrap
- inserts and updates
- cascade behavior
- index-backed query paths

## 2. Domain service tests

Validate:

- operation transitions
- scope validation
- job dependency checks
- finding dedupe
- memory ingestion filters

## 3. Tool contract tests

Validate:

- typed argument parsing
- target validation
- scope enforcement
- output normalization
- evidence generation

## 4. Scheduler tests

Validate:

- leasing
- stale worker recovery
- timeout handling
- cancellation
- retry behavior

## 5. Planner integration tests

Validate:

- planner proposal validation
- memory retrieval
- bounded sub-agent behavior
- finding updates

## 6. CLI integration tests

Validate:

- operation commands
- job inspection commands
- dashboard rendering
- findings and evidence views

## Suggested Team Order

If work is parallelized, the safest order is:

1. schema and repositories
2. scope service
3. typed tool contract
4. scheduler and workers
5. evidence and findings
6. planner and memory
7. CLI dashboard

This order keeps downstream work from being forced onto unstable abstractions.

## Definition of Done for V2

V2 is done when:

- operations replace tasks for red-team workflows
- scope policy is mandatory and enforced
- at least three typed tools run through the new runtime
- jobs execute concurrently with leasing and recovery
- evidence and findings are persisted and inspectable
- planners can propose jobs without bypassing execution controls
- the CLI can monitor live operations

V2 is not done when:

- prompts look better but execution is still shell-heavy
- tasks and jobs are blended together
- concurrency is simulated rather than scheduled
- memory is mostly transcript replay

## Immediate Next Build Slice

The best first implementation slice is:

1. create V2 schema
2. implement `OperationService`
3. implement `ScopePolicyService`
4. implement `JobService`
5. implement one typed tool:
   - `dns_lookup`
6. implement one worker that can claim and execute one job
7. expose:
   - `/operation create`
   - `/job list`

That slice is small enough to ship early and strong enough to validate the architecture.

## Final Recommendation

The project should treat V2 as a replacement program, not an incremental patch series on the old task runtime.

The right path is:

- establish the new schema
- enforce scope in code
- make tools typed
- build real concurrency
- add planner intelligence afterward

That order protects maintainability and keeps the red-team direction from collapsing into a prompt-driven shell wrapper.
