# Red-Team Agent Requirements Specification

## Purpose

This document defines the product and engineering requirements for evolving `red-code` from a local coding agent into a local agent for authorized security assessment and red-team-style workflows.

The target product is:

- local-first
- single-operator
- scope-bound
- auditable
- evidence-driven

The target product is not:

- an unrestricted offensive automation tool
- a multi-user SaaS platform
- a remote cloud control plane

## Product Positioning

The future runtime should support authorized security work such as:

- asset and service enumeration
- web surface inspection
- protocol and TLS inspection
- evidence collection
- finding generation and triage
- resumable operation tracking

The runtime must assume that every operation requires explicit authorization and explicit in-scope targets.

## Current Baseline

The current repository already provides useful foundations:

- local CLI shell
- explicit `SKILL.md` loading and activation
- centralized tool execution through `ToolExecutor`
- persisted `Task`, `Run`, checkpoint, and task-log records
- capability-tier safety controls
- resumable local execution

The current repository does not yet provide:

- scope-aware target enforcement
- typed security tools
- concurrent background jobs
- structured evidence and findings as first-class data
- a dedicated security-operation domain model

## Target Users

Primary users:

- security engineers
- red-team operators
- internal assessment staff

Secondary users:

- technical leads reviewing scope and results
- defenders consuming structured findings and evidence exports

## Primary Use Cases

1. Create an authorized operation against a declared target scope.
2. Run safe, typed enumeration and verification jobs within that scope.
3. Persist outputs as evidence artifacts and normalized summaries.
4. Convert evidence into candidate or confirmed findings.
5. Resume, inspect, pause, and export the operation later.

## Functional Requirements

### FR-01 Top-Level Operation Model

The runtime must replace or supersede generic task semantics with a security-oriented top-level entity named `Operation`.

An `Operation` must represent:

- one operator objective
- one approved target boundary
- one durable container for jobs, findings, evidence, and memory

Minimum fields:

- `id`
- `public_id`
- `title`
- `objective`
- `workspace`
- `status`
- `scope_policy_id`
- `created_at`
- `updated_at`
- `closed_at`
- `last_error`

Minimum statuses:

- `draft`
- `ready`
- `running`
- `paused`
- `blocked`
- `failed`
- `completed`
- `cancelled`

### FR-02 Scope Policy

Every executable operation must have a `ScopePolicy`.

The scope policy must support:

- allowed hosts
- allowed domains
- allowed CIDRs
- allowed ports
- allowed protocols
- denied targets
- allowed tool categories
- maximum concurrency
- request or packet rate limits
- actions requiring operator confirmation

Important rule:

- scope enforcement must happen in runtime code, not only in prompts or skill text

### FR-03 Job Execution Model

The runtime must introduce `Job` as the smallest schedulable execution unit.

A job must support:

- queued execution
- dependency tracking
- timeout
- cancellation
- retry policy
- per-job status
- per-job logs

Examples:

- one DNS lookup batch
- one HTTP probe against one target
- one TLS inspection
- one banner-grab step
- one constrained port scan

Minimum statuses:

- `pending`
- `queued`
- `running`
- `succeeded`
- `failed`
- `timed_out`
- `cancelled`
- `blocked`

### FR-04 Typed Security Tools

Security workflows must execute through typed tools instead of relying mainly on free-form shell commands.

The MVP tool set should include:

- `dns_lookup`
- `http_probe`
- `tls_inspect`
- `banner_grab`
- `port_scan`

Each typed tool must:

- accept structured arguments
- validate target format
- validate scope-policy compliance
- enforce rate and timeout limits
- return normalized structured output
- emit evidence candidates
- emit finding candidates when appropriate

### FR-05 Evidence Model

The runtime must persist `Evidence` as a first-class entity.

Evidence must represent durable proof such as:

- response headers
- body snippets
- DNS answers
- port-state samples
- TLS certificate details
- screenshots
- tool result summaries

Minimum evidence fields:

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

### FR-06 Finding Model

The runtime must persist `Finding` as a first-class entity derived from one or more pieces of evidence.

Minimum finding fields:

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

Minimum finding statuses:

- `open`
- `confirmed`
- `dismissed`
- `duplicate`
- `fixed`

### FR-07 Memory and Planning

The runtime must support structured memory instead of relying only on transcript checkpoints.

Memory must capture stable facts such as:

- discovered services
- relevant target characteristics
- reusable workflow rules
- summarized findings
- reporting preferences

Planner behavior must follow these rules:

- planners may propose jobs
- planners may summarize evidence and findings
- planners must not bypass typed tools
- planners must not widen target scope

### FR-08 Skill System Evolution

The existing skill system should be preserved, but its role should change.

Skills should remain useful for:

- workflow specialization
- prompt overlays
- tool visibility narrowing
- role-specific planning templates

Skills must not be treated as the primary security boundary.

The runtime should fully consume currently parsed-but-unused fields such as:

- `model`
- `effort`
- `shell`
- `user-invocable`
- `disable-model-invocation`

### FR-09 Safety and Approval

The runtime must be deny-by-default.

The runtime must hard-block:

- out-of-scope targets
- disallowed protocols
- disallowed ports
- disallowed tool categories
- unapproved sensitive actions

The runtime must log:

- policy denials
- approval requests
- approval outcomes
- blocked actions
- tool execution outcomes

### FR-10 Operator Interface

The CLI must support inspection of the new runtime entities.

Minimum command groups:

- `/operation`
- `/job`
- `/finding`
- `/evidence`
- `/dashboard`

The operator must be able to:

- create and inspect operations
- inspect scope policy
- list and inspect jobs
- inspect evidence
- inspect and triage findings
- monitor failures and blocked actions

### FR-11 Export

The runtime must support exportable summaries for:

- operation overview
- finding list
- evidence index

## Non-Functional Requirements

### NFR-01 Security

No network-capable execution may occur without a validated scope policy.

### NFR-02 Auditability

Every high-signal runtime action must be attributable to:

- operation
- job
- tool
- target
- time
- outcome

### NFR-03 Recoverability

Operation and job state must survive restarts without silent data loss.

### NFR-04 Local-First Storage

Metadata should remain in SQLite.
Large evidence artifacts should remain on the local filesystem.

### NFR-05 Extensibility

New security tools must be addable through a shared typed contract rather than ad hoc shell wrappers.

### NFR-06 Maintainability

The implementation should preserve clear boundaries between:

- CLI routing
- orchestration
- tool execution
- persistence
- reporting

## Out of Scope for MVP

The first red-team-oriented version does not need:

- multi-user collaboration
- distributed workers across hosts
- web UI
- browser automation
- unrestricted exploit automation

## MVP Definition

The MVP is complete when the runtime can:

1. create an operation with an enforced scope policy
2. schedule and run typed security jobs within that scope
3. persist evidence artifacts and metadata
4. persist candidate and confirmed findings
5. expose operation, job, evidence, and finding inspection through the CLI
6. hard-block out-of-scope actions and record the denial

## Acceptance Criteria

- an out-of-scope target is rejected before tool execution
- at least two job types can run under the scheduler
- every successful job creates at least one evidence record
- findings can be reviewed without reading raw transcripts
- high-risk actions always require approval or produce a denial event
- the operator can resume an interrupted operation and inspect its prior state

## Design Constraints

- legacy `Task` and `Run` behavior may remain during migration, but the red-team runtime should not be forced into those abstractions long-term
- typed tools are preferred over shell composition
- observability must remain easy to inspect as capability expands
- future sub-agent support must remain scope-bound and planner-only by default
