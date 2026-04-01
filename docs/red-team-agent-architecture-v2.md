# Red-Team Agent Architecture V2

## Document Goal

This document defines a concrete implementation plan for evolving `red-code` into a local red-team-oriented agent.

It assumes the following engineering policy:

- backward compatibility is not a design goal
- old abstractions may be removed when they block correctness
- refactors are encouraged when they improve clarity, safety, or maintainability
- no feature should be kept merely because it already exists

This is not a migration guide for preserving old behavior.
It is a target-state architecture document.

## Design Principles

### 1. Safety over convenience

The system must prefer hard denial over ambiguous execution.
If target scope, tool arguments, or job ownership are unclear, execution should stop.

### 2. Typed execution over prompt-driven shell habits

Red-team workflows must use first-class typed tools rather than asking the model to improvise shell commands.

### 3. Orchestration over chat-loop expansion

Parallel work must be implemented as a real job system, not as multiple free-floating model loops.

### 4. Structured evidence over free-form transcripts

Security work must produce findings, evidence, and normalized results as first-class data.

### 5. Replacement over compatibility shims

If an old runtime shape conflicts with the target design, replace it.
Do not add adapter layers that keep weak abstractions alive.

## Target Product Shape

The target system is a local single-operator red-team agent with:

- skill-defined offensive workflows
- scope-bound target policy
- typed security tools
- parent-task plus child-job orchestration
- concurrent background execution
- structured evidence and findings
- inspectable runtime dashboards
- resumable agent planning state

It is not a generic coding assistant with some security prompts added on top.

## Non-Goals

The following are explicitly out of scope for V2:

- preserving current command names if better names exist
- preserving current database schema
- preserving current checkpoint payload format
- preserving one-shell-equals-one-task runtime assumptions
- exposing unrestricted raw shell execution to red-team skills
- multi-user collaboration
- cloud orchestration
- browser or web UI before the runtime is stable

## Core Architectural Decision

The current architecture centers on:

- one interactive shell
- one active task
- one foreground run
- one conversational checkpoint

The V2 architecture must instead center on:

- one operation
- many jobs
- optional planner agents
- background workers
- typed tools
- structured findings
- explicit target scope

This changes the primary runtime unit from conversational turn execution to orchestrated operational execution.

## New Domain Model

V2 should replace the current runtime model with the following entities.

### Operation

`Operation` replaces the current concept of a user task as the top-level unit of work.

Purpose:

- represent one operator objective
- define the approved target boundary
- own all child jobs, findings, and evidence
- provide the durable execution context for a campaign or assessment step

Fields:

- `id`
- `public_id`
- `title`
- `objective`
- `workspace`
- `status`
- `scope_policy_id`
- `planner_profile`
- `memory_profile_id`
- `created_at`
- `updated_at`
- `closed_at`

Suggested statuses:

- `draft`
- `ready`
- `running`
- `paused`
- `blocked`
- `failed`
- `completed`
- `cancelled`

### ScopePolicy

`ScopePolicy` is mandatory.
No operation may execute network-capable jobs without one.

Purpose:

- define exactly what targets are in scope
- define allowed tool categories
- define rate and concurrency limits
- define protocol restrictions

Fields:

- `id`
- `operation_id`
- `allowed_hosts`
- `allowed_domains`
- `allowed_cidrs`
- `allowed_ports`
- `allowed_protocols`
- `denied_targets`
- `max_concurrency`
- `requests_per_minute`
- `packets_per_second`
- `requires_confirmation_for`
- `created_at`

Important rule:

- the scope policy must be enforced by the runtime, not described only in prompts

### PlannerRun

`PlannerRun` replaces the old `Run` abstraction for model-driven planning work.

Purpose:

- record one planner decision pass
- capture why jobs were created, updated, or cancelled
- persist the model-side reasoning artifacts that are safe to store

Fields:

- `id`
- `public_id`
- `operation_id`
- `status`
- `planner_kind`
- `input_summary`
- `decision_summary`
- `memory_snapshot_id`
- `started_at`
- `finished_at`
- `error_code`
- `error_message`

Suggested statuses:

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

### Job

`Job` is the central execution unit of the system.

Purpose:

- represent one concrete action
- be schedulable, cancellable, inspectable, and auditable
- isolate execution and output capture

Examples:

- one TCP port scan
- one directory scan
- one DNS lookup batch
- one HTTP probe sequence
- one CVE verification step

Fields:

- `id`
- `public_id`
- `operation_id`
- `parent_job_id`
- `planner_run_id`
- `job_type`
- `status`
- `priority`
- `target_ref`
- `tool_name`
- `args_json`
- `result_summary`
- `started_at`
- `finished_at`
- `timeout_seconds`
- `retry_count`
- `worker_id`
- `error_code`
- `error_message`

Suggested statuses:

- `pending`
- `queued`
- `running`
- `succeeded`
- `failed`
- `timed_out`
- `cancelled`
- `blocked`

### Evidence

`Evidence` stores normalized proof artifacts.

Purpose:

- persist machine-usable and human-usable proof
- separate durable findings from raw logs
- support reporting and later verification

Fields:

- `id`
- `operation_id`
- `job_id`
- `evidence_type`
- `target_ref`
- `title`
- `summary`
- `artifact_path`
- `content_type`
- `hash_digest`
- `captured_at`
- `metadata_json`

Examples:

- HTTP response headers
- response body snippet
- screenshot
- banner text
- DNS answer set
- port state sample

### Finding

`Finding` is a first-class security result.

Purpose:

- represent a meaningful issue or conclusion
- support triage, reporting, and operator follow-up

Fields:

- `id`
- `operation_id`
- `source_job_id`
- `finding_type`
- `title`
- `target_ref`
- `severity`
- `confidence`
- `status`
- `summary`
- `impact`
- `reproduction_notes`
- `next_action`
- `created_at`
- `updated_at`

Suggested statuses:

- `open`
- `confirmed`
- `dismissed`
- `duplicate`
- `fixed`

### MemoryProfile

`MemoryProfile` defines what long-lived context is available to planners and skills.

Purpose:

- capture stable operation rules
- capture operator preferences
- capture domain notes that are safe and useful to persist

Fields:

- `id`
- `operation_id`
- `profile_kind`
- `instruction_text`
- `tool_preferences_json`
- `reporting_preferences_json`
- `retention_policy_json`
- `created_at`
- `updated_at`

### MemoryEntry

`MemoryEntry` is a structured stored fact.

Purpose:

- avoid replaying full transcripts
- retain stable facts, not noisy conversation fragments

Fields:

- `id`
- `operation_id`
- `entry_type`
- `source_kind`
- `source_ref`
- `title`
- `body`
- `tags_json`
- `relevance_score`
- `created_at`

Recommended entry types:

- `operator_rule`
- `target_fact`
- `workflow_rule`
- `tool_observation`
- `finding_summary`
- `reporting_note`

## What Must Be Replaced

To reach this target cleanly, the following current concepts should be removed or substantially replaced.

### Replace `Task` with `Operation`

Reason:

- `Task` is too generic
- it does not carry scope as a first-class requirement
- it reflects interactive CLI ergonomics rather than operational semantics

### Replace `Run` with `PlannerRun`

Reason:

- the current run model conflates user interaction and execution
- V2 needs a planner record, not a generic bound-prompt record

### Add `Job` instead of stretching task checkpoints

Reason:

- concurrent work needs its own lifecycle
- scans and probes are not just conversational state transitions

### Replace generalized shell-heavy security execution with typed tools

Reason:

- raw shell execution is too hard to constrain and normalize
- logging intent and validating arguments becomes unreliable

### Replace transcript-first checkpointing with structured memory plus planner state

Reason:

- raw transcript restoration does not scale to complex security workflows
- red-team work needs durable facts, findings, and evidence more than chat history

## Runtime Architecture

V2 should be divided into these layers.

## 1. Command Layer

Responsible for:

- CLI command parsing
- operation creation and inspection
- dashboard views
- operator confirmations

Suggested commands:

- `/operation create`
- `/operation list`
- `/operation show <id>`
- `/operation pause <id>`
- `/operation resume <id>`
- `/job list <operation_id>`
- `/job show <job_id>`
- `/job cancel <job_id>`
- `/dashboard`
- `/finding list <operation_id>`
- `/evidence list <operation_id>`

The command layer must not directly orchestrate scanning logic.

## 2. Planner Layer

Responsible for:

- reading operation memory
- deciding what jobs to create
- deciding what follow-up jobs are justified
- summarizing job outcomes into findings and new memory

Important rule:

- planners may propose jobs, but they do not execute tools directly

Planner types may include:

- `interactive_planner`
- `autonomous_planner`
- `skill_specialized_planner`

## 3. Orchestration Layer

Responsible for:

- job scheduling
- dependency resolution
- worker assignment
- retries
- cancellation
- timeout enforcement
- aggregation

Core services:

- `OperationService`
- `ScopePolicyService`
- `PlannerService`
- `JobService`
- `SchedulerService`
- `EvidenceService`
- `FindingService`
- `MemoryService`

## 4. Worker Layer

Responsible for:

- executing one job through one typed tool
- capturing normalized output
- writing evidence
- reporting job completion or failure

Workers should be isolated from planner prompts and interactive shell concerns.

## 5. Tool Layer

Responsible for:

- typed security tool interfaces
- argument validation
- scope enforcement hooks
- normalized result production

Required initial tools:

- `port_scan`
- `dir_scan`
- `http_probe`
- `dns_lookup`
- `tls_inspect`
- `banner_grab`
- `cve_check`

Optional later tools:

- `screenshot_capture`
- `web_fingerprint`
- `subdomain_enum`
- `content_fetch`

## 6. Persistence Layer

Responsible for:

- SQLite metadata
- artifact blob storage
- durable job state
- evidence indexing
- memory storage

## Typed Tool Contract

Every security tool must implement a shared contract.

### Input contract

Each tool receives:

- `operation_id`
- `job_id`
- `target`
- `validated_scope`
- `typed_args`
- `execution_limits`

### Validation contract

Each tool must validate:

- target format
- protocol compatibility
- port and path arguments
- rate and timeout limits
- scope-policy compliance

### Output contract

Each tool returns:

- `status`
- `summary`
- `structured_result`
- `evidence_items`
- `finding_candidates`
- `metrics`

### Forbidden behavior

Tools must not:

- emit only raw stdout as their primary result
- bypass scope validation
- invoke unrestricted shell commands without wrapper approval
- write artifacts outside managed storage

## Memory Architecture

V2 memory must be layered rather than monolithic.

### 1. Policy Memory

Stores stable operational rules:

- approved targets
- forbidden actions
- evidence requirements
- reporting conventions

This is the replacement for a generic project memory file.

### 2. Working Memory

Stores current campaign facts:

- live hosts
- known services
- enumerated paths
- failed attempts worth avoiding

This should be compact and queryable.

### 3. Evidence Memory

Stores links to proof artifacts and normalized summaries.

### 4. Findings Memory

Stores confirmed or candidate findings that should influence future planning.

### Memory ingestion rules

Memory should not be appended from every planner response.

A memory write should happen only when content is:

- stable
- reusable
- actionable
- safe to retain

### Memory retrieval rules

Planner context should be composed from:

- policy memory
- recent high-value evidence
- open findings
- relevant working-memory facts

Never reconstruct full transcript history by default.

## Sub-Agent Architecture

V2 should support sub-agents, but in a constrained form.

### Key decision

A sub-agent is a planner context with bounded authority, not an independent unrestricted agent.

### Allowed sub-agent roles

- `recon_coordinator`
- `web_enum_planner`
- `network_surface_planner`
- `vuln_validation_planner`
- `report_synthesis_planner`

### Boundaries

A sub-agent may:

- read operation memory
- inspect job summaries
- propose child jobs
- synthesize findings

A sub-agent may not:

- directly widen scope
- directly bypass typed tools
- directly execute unrestricted shell actions

### Execution model

Sub-agent flow:

1. parent planner delegates a bounded objective
2. delegated planner receives scoped memory and allowed tool categories
3. delegated planner emits job proposals or finding updates
4. orchestration layer validates proposals
5. scheduler enqueues approved jobs

This keeps sub-agents useful without turning them into uncontrolled parallel chat sessions.

## Safety Architecture

Safety must move from generic capability tiers to scope-aware policy enforcement.

### Existing capability tiers are insufficient

`read / write / execute / destructive` are still useful as secondary metadata, but not as the primary safety model for red-team execution.

### Primary policy dimensions

The new safety model must enforce:

- target scope
- protocol scope
- tool category scope
- concurrency limits
- rate limits
- artifact retention policy
- confirmation rules for sensitive actions

### Enforcement points

Policy must be enforced in:

- command validation
- planner proposal validation
- scheduler admission
- tool execution
- evidence storage

### Default posture

The default posture must be deny-by-default.

If a target is not explicitly allowed, it is out of scope.

## Scheduler and Concurrency Model

Concurrency should be implemented as a proper scheduler.

### Scheduler responsibilities

- admit jobs
- check dependencies
- enforce scope and limits
- pick workers
- record heartbeat
- retry safe failures
- stop jobs on timeout

### Queue design

At minimum:

- one persistent job queue in SQLite
- one worker heartbeat table
- one lease mechanism for claimed jobs

### Dependency model

Jobs should support:

- no dependency
- depends on one job
- depends on a set of jobs

Example:

- `http_probe` may depend on a successful `port_scan`
- `cve_check` may depend on service fingerprint evidence

### Retry model

Retries should be explicit per job type.

Do not retry:

- out-of-scope failures
- invalid arguments
- policy denials

Retryable examples:

- transient DNS failure
- connection reset
- worker crash before completion writeback

## Evidence and Findings Pipeline

The runtime should promote normalized outputs into durable artifacts through a fixed pipeline.

### Pipeline

1. tool executes
2. tool returns structured result
3. evidence items are materialized into artifact storage
4. finding candidates are emitted
5. planner reviews candidates when needed
6. findings are confirmed, merged, or dismissed

### Why this matters

This separates:

- raw execution output
- durable proof
- analyst conclusion

That separation is essential for maintainability and reporting quality.

## Storage Design

SQLite is still a reasonable metadata store for V2.

Recommended storage split:

- SQLite for operations, policies, planner runs, jobs, findings, memory, and indexes
- filesystem blobs for large evidence artifacts

Suggested artifact directories:

- `.red-code/operations/<operation_id>/evidence/`
- `.red-code/operations/<operation_id>/planner/`
- `.red-code/operations/<operation_id>/exports/`

The old generic checkpoint directory should not remain the center of runtime persistence.

## Suggested Module Layout

```text
src/
  command/
    cli.py
    operation_commands.py
    job_commands.py
    dashboard.py
  domain/
    operations/
    scope/
    planners/
    jobs/
    findings/
    evidence/
    memory/
  orchestration/
    scheduler.py
    worker_manager.py
    planner_runtime.py
    admission.py
  tools/
    security/
      port_scan.py
      dir_scan.py
      http_probe.py
      dns_lookup.py
      tls_inspect.py
      cve_check.py
    contracts.py
    registry.py
  storage/
    sqlite.py
    repositories/
      operations.py
      scope_policies.py
      planner_runs.py
      jobs.py
      findings.py
      evidence.py
      memory.py
      workers.py
  runtime/
    worker.py
    leases.py
    timeouts.py
  reporting/
    findings_summary.py
    evidence_export.py
```

## Migration Strategy

Because compatibility is not a goal, migration should optimize for correctness and implementation speed.

### Recommended approach

1. freeze the old task runtime as legacy
2. build the V2 runtime beside it
3. switch the CLI entry points to the V2 runtime
4. remove the legacy runtime after feature parity for core operation flows

### Explicitly avoid

- dual-write across old and new schemas for long periods
- compatibility adapters that translate `Task` into `Operation` at every boundary
- keeping generic `bash` as a first-class red-team execution primitive

### One acceptable short-lived compatibility measure

It is acceptable to keep the old runtime available behind a clearly marked legacy command group during development.

That is a temporary product partition, not an architectural compatibility promise.

## Implementation Phases

## Phase 1: Domain Reset

Deliverables:

- add `Operation`, `ScopePolicy`, `Job`, `Evidence`, `Finding`, `MemoryEntry`
- add fresh SQLite schema and repositories
- add artifact storage layout under operations

Exit criteria:

- operations can be created and inspected
- scope policies can be persisted and validated
- jobs can be created and listed

## Phase 2: Typed Tool Foundation

Deliverables:

- implement security tool contract
- implement `port_scan`, `http_probe`, `dns_lookup`
- add strict argument validation
- add normalized result schema

Exit criteria:

- tools execute only through typed wrappers
- tools reject out-of-scope requests
- evidence artifacts are persisted correctly

## Phase 3: Scheduler and Workers

Deliverables:

- persistent queue
- worker lease system
- timeout handling
- cancellation handling
- retry policy

Exit criteria:

- multiple jobs can run concurrently
- worker crashes do not corrupt job state
- timed-out jobs are reclaimed safely

## Phase 4: Planner and Memory

Deliverables:

- planner runtime
- `PlannerRun`
- policy-memory and working-memory retrieval
- controlled sub-agent delegation

Exit criteria:

- planner can read memory and create jobs
- planner can summarize evidence into findings
- delegated planners cannot bypass scope

## Phase 5: Dashboards and Reporting

Deliverables:

- `/dashboard`
- operation monitor view
- findings list view
- evidence inspection view
- exportable summaries

Exit criteria:

- operator can observe live concurrent work
- findings can be reviewed without reading raw logs

## Testing Strategy

V2 should be tested at four levels.

### 1. Domain tests

Validate:

- operation transitions
- policy validation
- job dependency rules
- finding merge rules

### 2. Tool contract tests

Validate:

- argument validation
- scope enforcement
- normalized output shape
- evidence generation

### 3. Scheduler tests

Validate:

- leasing
- retries
- heartbeats
- cancellation
- timeouts

### 4. End-to-end operation tests

Validate:

- planner creates jobs
- workers execute jobs
- evidence is stored
- findings are produced
- dashboards reflect current state

## Deletion List

The following legacy assumptions should be deleted once V2 is active:

- one active task bound to one shell
- one prompt equals one meaningful unit of runtime work
- checkpoint blob as the main durable state of security workflows
- raw shell as the main execution surface for offensive tooling
- skill prompt as the primary safety mechanism

## Final Recommendation

The correct way to build a serious red-team agent on this codebase is not to gradually stretch the current task loop.

The correct approach is to introduce a new runtime center:

- `Operation` for operator intent
- `ScopePolicy` for hard safety boundaries
- `PlannerRun` for model decisions
- `Job` for concrete execution
- `Evidence` for proof
- `Finding` for conclusions
- `MemoryEntry` for durable reusable context

Sub-agents and memory should absolutely be reused as ideas from mature agent systems, but only after they are transformed into:

- bounded planner delegation
- structured operational memory
- scope-aware orchestration

If that replacement is done cleanly, the project can become a credible local red-team agent.
If the system keeps growing by layering security prompts onto the old task runtime, complexity and risk will rise faster than capability.
