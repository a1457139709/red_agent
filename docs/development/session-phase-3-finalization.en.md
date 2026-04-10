# Phase 3 Finalization: Foreground Execution Closure

## Purpose

This document closes the design loop for **Phase 3: Foreground Execution Closure**.

It converts the earlier Phase 3 planning guidance into a fixed implementation baseline. After this document, Phase 3 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the foreground-first execution model
- the execution service boundary
- the progress event model
- the controller/execution integration boundary
- the demotion of manual operator-triggered execution
- the rejection of unnecessary execution designs

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 2 Finalization](D:\Project\Python\Agent\docs\development\session-phase-2-finalization.en.md)
- [Phase 3 Implementation Checklist](D:\Project\Python\Agent\docs\development\session-phase-3-implementation-checklist.en.md)

## Phase 3 Status

Phase 3 is now **architecturally converged**.

This means:

- the execution boundary is settled
- the foreground-first runtime direction is settled
- the main unresolved product-loop decisions are closed
- coding can begin without reopening the execution model

## Replacement Position of Phase 3

Phase 3 is the point where the old red-team execution model is replaced in **product runtime terms**.

After Phase 3:

- red-team work executes from the current interactive flow
- the product no longer depends on a separate manual run stage
- worker and scheduler concepts remain internal

This is also the point where legacy top-level execution paths become eligible for physical cleanup in later phases.

## Final Decisions

## 1. Foreground-First Execution Model

Final decision:

- red-team execution is foreground-first

Meaning:

- execution starts from the current interactive flow
- progress is visible while the run is happening
- results return to the same session

Not allowed:

- making background or detached execution the default user experience

## 2. Execution Service Boundary

Final decision:

- foreground execution is exposed through an application-layer execution service

Recommended location:

- `src/app/execution_service.py`

Responsibility:

- accept session-aware execution requests
- orchestrate foreground execution
- update session state
- surface structured execution outcomes to the controller

Not allowed:

- letting controllers call raw worker or scheduler primitives directly as the product-facing execution path

## 3. Foreground Runner Boundary

Final decision:

- foreground runtime mechanics live in a dedicated runtime module

Recommended location:

- `src/runtime/foreground_runner.py`

Responsibility:

- run foreground execution steps
- emit structured progress events
- handle failure and completion paths

## 4. Progress Event Model

Final decision:

Phase 3 uses structured progress events.

Recommended location:

- `src/runtime/execution_events.py`

Minimum event types:

```text
execution_started
step_started
step_completed
step_failed
execution_paused
execution_completed
execution_failed
```

This progress model must be stable enough for:

- CLI rendering
- future Web UI use
- later record retrieval

## 5. Controller Integration Policy

Final decision:

- the Agent Controller triggers execution through `ExecutionService`

The controller may:

- request execution
- receive progress or execution results
- translate those into adapter-safe outputs

The controller may not:

- become the execution engine
- own low-level runtime loops

## 6. CLI Role During Execution

Final decision:

The CLI remains an adapter during execution.

The CLI may:

- render progress
- render completion
- render failure

The CLI may not:

- own the execution state machine
- execute steps directly
- infer structured progress by parsing model prose

## 7. Internal Job Engine Policy

Final decision:

Jobs, workers, schedulers, leases, and retries remain valid **internal** runtime concepts.

They may still be reused for:

- orchestration
- retries
- typed-tool execution
- safety and scope handling

They are not:

- product-facing execution concepts
- part of the default user path

## 8. Manual Multi-Step Execution Policy

Final decision:

The old operator-driven sequence:

- create top-level work
- apply workflow
- trigger a separate run stage

is no longer the default product execution model.

### REWRITE REQUIRED

This design is explicitly replaced by foreground execution closure.

It may remain temporarily for internal or debug use only, but it is no longer a valid target architecture path.

## 9. Progress Visibility Policy

Final decision:

Users must be able to observe:

- that execution started
- what step is running
- whether a step completed or failed
- when execution finished

This visibility must come from structured runtime events, not only from free-form model narration.

## 10. Error and Failure Policy

Final decision:

Foreground execution failures must be returned as structured execution outcomes.

Not allowed:

- failures disappearing only into internal worker logs
- the interactive session stopping with no execution-level explanation

## 11. Session State Policy During Execution

Final decision:

The execution service updates session status during the foreground lifecycle.

Minimum expectation:

- entering execution moves the session into `active`
- terminal execution outcomes map to terminal session updates where appropriate
- execution failures surface through `last_error`

The exact mapping may be refined later, but Phase 3 must not leave session state untouched during execution.

## 12. Rejected Designs

The following designs are explicitly rejected and should be discarded.

### Rejected: User-Facing Worker Control

Reason:

- workers are internal engine machinery, not product concepts

### Rejected: Scheduler-First UX

Reason:

- the product is foreground-first, not queue-first

### Rejected: Background-Only Default Runtime

Reason:

- it conflicts with the target Claude-Code-like interaction model

### Rejected: Transcript-Only Progress

Reason:

- progress must be structured for adapters and future retrieval

### Rejected: Mandatory Planner Gate Before Execution

Reason:

- Phase 3 must support direct foreground execution without requiring a separate planner object first

## Final Module Plan for Phase 3

New Phase 3 modules:

- `src/runtime/execution_events.py`
- `src/runtime/foreground_runner.py`
- `src/app/execution_service.py`

Expected touched files:

- `src/controller/agent_controller.py`
- `src/controller/contracts.py`
- `src/main.py`
- optionally `src/cli/adapter.py`
- `src/cli/ui.py`
- relevant docs under `docs/`

Internal modules to reuse:

- `src/runtime/worker.py`
- `src/orchestration/scheduler.py`
- `src/orchestration/job_service.py`
- `src/app/security_tool_execution_service.py`
- `src/app/scoped_execution_service.py`
- `src/orchestration/scope_validator.py`

## Final Implementation Order

Phase 3 coding order is fixed as:

1. implement execution event types
2. implement the foreground runner
3. implement the execution service
4. integrate the controller with execution
5. integrate CLI progress rendering
6. demote the old manual multi-step execution flow from the primary product path

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Testing Plan for Phase 3

Recommended new test files:

- `tests/test_execution_events.py`
- `tests/test_foreground_runner.py`
- `tests/test_execution_service.py`

Required test areas:

### Progress Events

- stable event construction
- event payload completeness

### Foreground Runner

- success path
- failure path
- interruption path

### Execution Service

- session-aware execution orchestration
- session status updates
- structured final outcomes

### Controller Integration

- controller-triggered execution
- progress event propagation
- result propagation to the adapter

## Final Legacy Boundary

### REWRITE REQUIRED

The primary red-team execution path must not depend on:

- manual worker invocation
- manual scheduler invocation
- a second user-triggered run stage after setup

### Allowed Temporary Boundary

Allowed during migration:

- internal testing through old operator flows
- advanced debug access to old execution paths

Not allowed:

- documenting old execution flows as the recommended red-team path
- leaving the default runtime dependent on manual operator execution steps

## Phase 3 Ready-to-Implement Checklist

Phase 3 is now considered fully converged if the team accepts the following locked decisions:

- red-team execution is foreground-first
- `ExecutionService` is the application-layer execution boundary
- `ForegroundRunner` is the runtime execution loop
- progress is represented through structured events
- the controller triggers execution through the execution service
- the CLI renders progress but does not own execution logic
- the old manual multi-step execution workflow is no longer the default product path
- user-facing worker and scheduler concepts are discarded from the main UX

This checklist is now the Phase 3 baseline.
