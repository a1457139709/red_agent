# RETIRED DOCUMENT

# Phase 3 Implementation Checklist: Foreground Execution Closure

## Purpose

This document breaks down **Phase 3: Foreground Execution Closure** into implementation-ready engineering tasks.

It is intended to answer:

- what must be built in Phase 3
- which modules should be introduced
- which existing modules should be reused internally
- which legacy execution patterns must be discarded
- in what order the work should be implemented

This checklist assumes:

- Phase 1 has converged around the `session` domain model
- Phase 2 has converged around the Agent Controller and CLI adapter split

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 1 Finalization](D:\Project\Python\Agent\docs\development\session-phase-1-finalization.en.md)
- [Phase 2 Finalization](D:\Project\Python\Agent\docs\development\session-phase-2-finalization.en.md)

## Phase Goal

Make red-team workflows execute and report progress in the **current interactive session** so the user no longer experiences a split between:

- setup
- planning
- execution
- result review

Phase 3 establishes the first complete product loop for the new architecture.

## Scope of Phase 3

This phase covers:

- foreground execution for red-team sessions
- execution service introduction
- progress event model
- integration between controller and execution runtime
- internal reuse of jobs, workers, and scheduler as implementation details
- session-visible execution progress and result handoff

This phase does **not** yet require:

- risk-based confirmation policy implementation
- final skill/module unification
- final `memory/` / `artifacts/` / `findings/` / `reports/` split
- full report retrieval flows
- Web UI implementation

## Non-Goals

Do not do the following in Phase 3:

- keep a manual "create now, run later" red-team workflow as the default product path
- expose worker, lease, queue, or scheduler concepts to the user
- require users to run a separate execution command after session setup
- make background execution the primary product experience
- force planner mode before any foreground execution can begin

## Rewrite Policy

### REWRITE REQUIRED

Phase 3 is a **runtime execution rewrite** for the user-facing red-team loop.

The implementation should prefer:

- a foreground-first execution service
- progress reporting in the current session
- session-level orchestration
- internal reuse of jobs and workers without exposing them

The implementation should avoid:

- preserving the old operator-facing `/operation -> /skill apply -> external worker run` loop
- exposing raw job engine mechanics as part of the product model
- making the user responsible for driving the execution state machine manually

## Designs Explicitly Rejected in Phase 3

The following designs are not needed for the target product and should be discarded.

### 1. Manual Secondary Run Stage

Rejected design:

- user creates work in one step and must manually trigger a separate runtime stage afterward

Reason:

- this is the exact gap Phase 3 exists to remove

### 2. Worker-First User Experience

Rejected design:

- users interact with workers, queues, leases, or scheduler passes directly

Reason:

- those are internal engine concepts, not product-facing concepts

### 3. Background-Only Execution

Rejected design:

- red-team execution is treated primarily as a detached background process

Reason:

- the target product is foreground-first and Claude-Code-like in feel

### 4. Transcript-Only Progress Tracking

Rejected design:

- progress exists only as free-form model text with no structured runtime event model

Reason:

- progress must be structured enough for adapters, future Web UI, and reliable retrieval

### 5. Planner-As-Required-Gate

Rejected design:

- no execution may happen until a planner object exists

Reason:

- Phase 3 needs a direct foreground execution path, not a planner-dependent path

## Target Outcomes

By the end of Phase 3:

1. A red-team session can execute from the current interactive flow.
2. The controller can initiate execution through an execution service.
3. Progress is visible during execution.
4. Results are returned to the current session without a separate operator-controlled run step.
5. Internal jobs and workers remain reusable but hidden from the default user path.

## Module Strategy

## Modules to Introduce

These modules should be added in Phase 3.

### Application Service Layer

Recommended files:

- `src/app/execution_service.py`
- `src/app/execution_progress_service.py` or equivalent if progress concerns are separated

### Runtime Layer

Recommended files:

- `src/runtime/foreground_runner.py`
- `src/runtime/execution_events.py`

### Responsibilities

#### `execution_service.py`

Own the public execution contract for the application layer:

- start foreground execution for a session
- coordinate session-aware execution flow
- delegate actual work to the runtime layer
- translate execution results into session-level outcomes

#### `foreground_runner.py`

Own the runtime mechanics of foreground execution:

- step execution loop
- progress event emission
- error handling
- handoff to lower-level job or typed-tool paths

#### `execution_events.py`

Define structured progress events such as:

- execution started
- step started
- step completed
- step failed
- execution paused
- execution finished

## Existing Modules to Reuse Internally

These should remain reusable as internal execution primitives.

- `src/runtime/worker.py`
- `src/orchestration/scheduler.py`
- `src/orchestration/job_service.py`
- `src/app/security_tool_execution_service.py`
- `src/app/scoped_execution_service.py`
- `src/orchestration/scope_validator.py`
- `src/tools/security/`

Phase 3 should integrate with them only through a session-facing execution service contract.

## Existing Modules to Rewrite or Integrate

### REWRITE REQUIRED: Controller Integration

Affected files:

- `src/controller/agent_controller.py`
- `src/controller/contracts.py`

Action:

- the controller must gain a real execution path, not just session routing

### REWRITE REQUIRED: CLI Runtime Flow

Affected files:

- `src/main.py`
- optionally `src/cli/adapter.py`
- `src/cli/ui.py`

Action:

- the CLI must render execution progress in the current session
- the runtime must no longer stop after setup or planning

### REWRITE REQUIRED: Legacy Operator Red-Team Flow

Affected areas:

- any flow that still assumes manual operator execution after session setup

Action:

- demote to internal or legacy-only paths

## File-Level Checklist

## 1. Add the Execution Event Contract

Files:

- `src/runtime/execution_events.py`
- optionally `src/controller/contracts.py`

Checklist:

- define event types
- define event payloads
- define session-safe progress serialization

Completion check:

- execution progress can be represented without raw worker-specific terms

## 2. Add the Foreground Runner

Files:

- `src/runtime/foreground_runner.py`

Checklist:

- accept a session identifier or session object
- execute a foreground runtime loop
- emit structured progress events
- return structured completion results
- handle failure and interruption paths

Completion check:

- a session execution run can happen inside the interactive loop without requiring a separate operator command

## 3. Add the Execution Service

Files:

- `src/app/execution_service.py`

Checklist:

- expose a session-facing execution API
- call the foreground runner
- integrate with `SessionService`
- update session status during execution lifecycle
- surface structured results back to the controller

Completion check:

- higher-level runtime code can execute sessions without talking directly to worker primitives

## 4. Integrate Controller and Execution

Files:

- `src/controller/agent_controller.py`
- `src/controller/contracts.py`

Checklist:

- add execution request handling
- connect redteam session requests to execution
- return execution progress and final results as controller outputs

Completion check:

- the controller can drive end-to-end redteam flow beyond just setup

## 5. Integrate CLI Progress Rendering

Files:

- `src/main.py`
- `src/cli/ui.py`
- optionally `src/cli/adapter.py`

Checklist:

- render execution progress
- render final execution result
- keep rendering logic separate from execution logic

Completion check:

- the user can see execution happen inside the current session

## 6. Demote Legacy Manual Execution Paths

Files:

- `src/main.py`
- help output
- docs

Checklist:

- stop documenting manual multi-step execution as the default path
- mark operator-only execution paths as advanced or legacy
- ensure foreground execution is the main demonstrated flow

Completion check:

- the default documented red-team workflow is now foreground-first

## Progress Model Checklist

Phase 3 must define a minimal progress vocabulary.

Recommended event types:

- `execution_started`
- `step_started`
- `step_completed`
- `step_failed`
- `execution_paused`
- `execution_completed`
- `execution_failed`

Recommended event payload fields:

- `session_id`
- `session_public_id`
- `step_type`
- `step_label`
- `target_summary`
- `message`
- `timestamp`

## Execution Model Checklist

Phase 3 should define the minimum execution loop behavior.

### Start

- execution begins from the current interactive flow

### Run

- steps execute one by one in the foreground
- the runtime emits progress

### Error Handling

- failures must be surfaced as structured outcomes
- failures must not disappear into internal worker-only logs

### Completion

- completion returns a structured session-level result

## Adapter Boundary Checklist

The adapter should:

- trigger controller execution
- render progress events
- render final results

The adapter should not:

- run execution logic itself
- coordinate jobs directly
- own retry or failure policy
- infer progress by parsing free-form text

## Migration Sequence

Work should be performed in this order.

### Step 1. Freeze the Execution Contract on Paper

Before coding:

- finalize execution service responsibilities
- finalize progress event types
- finalize runner/service/controller boundaries

Reason:

- avoid scattering execution logic across runtime layers

### Step 2. Add the Execution Event Model

Reason:

- progress must be structured before it can be rendered consistently

### Step 3. Add the Foreground Runner

Reason:

- foreground runtime mechanics should exist before application orchestration is built on top

### Step 4. Add the Execution Service

Reason:

- session-aware orchestration belongs in the application layer

### Step 5. Integrate the Controller

Reason:

- Phase 3 only becomes real once the top-level runtime can trigger foreground execution

### Step 6. Integrate the CLI Adapter

Reason:

- execution closure is only visible once progress and results appear in the current interactive flow

### Step 7. Demote Legacy Multi-Step Execution Paths

Reason:

- product behavior must match the new execution contract

## Deletion and Deprecation Checklist

Phase 3 should not necessarily delete all internal job machinery, but it must delete obsolete product assumptions.

### Demote from Primary Flow

- explicit user-facing worker invocation
- explicit user-facing scheduler invocation
- any red-team flow that ends after setup and requires a second run step

### Keep as Internal Only

- worker runtime
- scheduler
- jobs
- lease and retry machinery

### Not Allowed

- documenting raw job engine concepts as part of the main user journey
- requiring the user to understand internal execution primitives

## Testing Checklist

## Unit Tests

Recommended new test files:

- `tests/test_execution_events.py`
- `tests/test_foreground_runner.py`
- `tests/test_execution_service.py`

Recommended checks:

- event construction
- foreground runner success and failure behavior
- session status updates during execution

## Integration Tests

Recommended checks:

- controller + execution service integration
- execution service + session service integration
- CLI adapter + progress rendering integration

## Regression Protection

Add tests that ensure:

- red-team execution no longer requires a manual secondary run step
- progress events are structured rather than transcript-only
- the main red-team flow does not expose worker-specific concepts

## Phase 3 Exit Review

Phase 3 should be considered complete only if all questions below can be answered with "yes".

1. Can a red-team session execute from the current interactive flow?
2. Is progress visible in the current session?
3. Does the controller trigger execution through an execution service rather than through ad hoc runtime calls?
4. Are worker and scheduler concepts hidden from the default user path?
5. Has the old manual multi-step execution workflow been demoted from the primary product path?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 3 are:

- `src/runtime/execution_events.py`
- `src/runtime/foreground_runner.py`
- `src/app/execution_service.py`
- controller integration for execution
- CLI progress rendering integration
- updated docs showing foreground execution as the default red-team flow

If any of these are missing, Phase 3 is not yet complete as an architecture step.
