# RETIRED DOCUMENT

# Phase 2 Finalization: Controller-First CLI and Intent Flow

## Purpose

This document closes the design loop for **Phase 2: Controller-First CLI and Intent Flow**.

It converts the earlier Phase 2 planning guidance into a fixed implementation baseline. After this document, Phase 2 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the controller boundary
- the adapter/controller split
- the top-level intent set
- the clarification model
- the role of slash commands
- the rewrite boundary for `src/main.py`

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 2 Implementation Checklist](D:\Project\Python\Agent\docs\development\session-phase-2-implementation-checklist.en.md)
- [Phase 1 Finalization](D:\Project\Python\Agent\docs\development\session-phase-1-finalization.en.md)

## Phase 2 Status

Phase 2 is now **architecturally converged**.

This means:

- the runtime entry boundary is settled
- the CLI/controller split is settled
- the main unresolved design choices are closed
- coding can begin without reopening the top-level interaction model

## Replacement Position of Phase 2

Phase 2 is the point where `task` and `operation` are replaced in **product entry and UX terms**.

After Phase 2:

- the primary runtime entry path is natural language routed through the Agent Controller
- `/task` and `/operation` are no longer the main way users start work
- legacy top-level commands may still exist temporarily, but only as advanced or debug paths

This means the top-level replacement is complete from the user's perspective, even if some legacy code still remains in the repository during migration.

## Final Decisions

## 1. Primary Entry Model

Final decision:

- natural language is the default user entry path

This means:

- plain text input is routed into the controller first
- slash commands are no longer the default product interaction model

Not allowed:

- keeping slash commands as the first-class user experience
- treating natural language as only a convenience wrapper

## 2. Controller Boundary

Final decision:

- the runtime introduces a dedicated Agent Controller layer

Recommended location:

- `src/controller/agent_controller.py`

Responsibility:

- own top-level request routing
- classify intent
- request clarification
- resolve session mode
- create or retrieve sessions through `SessionService`
- produce structured adapter-safe outputs

Not allowed:

- implementing this boundary only through prompt text
- spreading its responsibilities between `main.py`, `ui.py`, and ad hoc helpers

## 3. Controller Package Layout

Final decision:

Phase 2 introduces a dedicated controller package:

```text
src/controller/
  agent_controller.py
  intents.py
  clarification.py
  contracts.py
```

Rationale:

- the controller is a first-class runtime boundary
- it should not be hidden inside `src/main.py`

## 4. CLI Role

Final decision:

The CLI is an **adapter**, not the workflow owner.

The CLI may:

- read input
- display clarification requests
- display controller output
- route advanced commands

The CLI may not:

- decide top-level mode routing
- create sessions directly
- own intent classification
- own clarification policy

## 5. `src/main.py` Role

Final decision:

`src/main.py` becomes a thin composition and shell wiring module.

It may:

- bootstrap settings and services
- create the CLI adapter and controller
- run the event loop
- route advanced slash commands

It may not remain:

- the permanent owner of top-level product logic

### REWRITE REQUIRED

This is a required rewrite boundary.

The existing command-heavy routing style in `src/main.py` is not the target design.

## 6. Intent Set

Final decision:

Phase 2 defines the following top-level intent categories:

```text
normal_request
redteam_request
record_lookup_request
advanced_command_request
clarification_required
unsupported_request
```

Meaning:

- `normal_request`
  - general-purpose or temporary work
- `redteam_request`
  - persistent target-oriented security workflow
- `record_lookup_request`
  - asks about prior work, status, or results
- `advanced_command_request`
  - explicit slash command path
- `clarification_required`
  - missing information prevents safe routing
- `unsupported_request`
  - outside the supported top-level runtime model

## 7. Clarification Policy

Final decision:

Clarification is a first-class runtime behavior owned by the controller.

It is not:

- a UI-side trick
- an emergent prompt behavior with no contract

The controller must be able to return a structured clarification request when:

- the target is missing
- the request is security-flavored but underspecified
- the system cannot determine whether the request is temporary or persistent
- record lookup scope is ambiguous

## 8. Clarification Minimum Cases

Final decision:

Phase 2 must explicitly support clarification for these minimum cases.

### Bare Target Input

Example:

- `look at example.com`

Controller goal:

- determine whether the user wants temporary inspection or a redteam session

### Generic Security Request

Example:

- `scan this host`

Controller goal:

- obtain the target
- determine normal vs redteam mode

### Explicit Persistent Security Request

Example:

- `start a recon session for example.com`

Controller goal:

- gather the minimum information required to create the session cleanly

### Record Lookup Request

Example:

- `what did you already do`

Controller goal:

- determine which session or recent context the request refers to

## 9. Session Routing Policy

Final decision:

The controller owns the decision between:

- normal session flow
- redteam session flow

Routing rules:

- normal requests go to normal mode
- persistent target-oriented security requests go to redteam mode
- ambiguous requests stop for clarification

This routing decision must not live in:

- the CLI adapter
- presentation helpers
- slash command routing tables

## 10. Slash Command Policy

Final decision:

Slash commands remain available, but only as:

- advanced operator controls
- debug surfaces
- temporary migration support

They are not the default product path.

### Demoted from Primary UX

- `/task`
- `/operation`
- `/job`
- `/planner`

These may remain reachable during migration, but they are not part of the target first-use experience.

## 11. Help and Onboarding Policy

Final decision:

Help and startup guidance must present natural language first.

The UI should:

- show plain-language examples before slash command lists
- describe normal and redteam modes in user terms
- move slash-command explanations into advanced help sections

## 12. Adapter/Controller Contract

Final decision:

The CLI and future Web UI must talk to the controller through structured contracts.

Recommended file:

- `src/controller/contracts.py`

Minimum contract types:

- `ControllerRequest`
- `ControllerResult`
- `ClarificationRequest`
- `ClarificationAnswer` or equivalent follow-up type

These contracts should be adapter-safe and should not expose CLI-specific assumptions.

## 13. Phase 2 Controller Output Policy

Final decision:

The controller may return structured outcomes such as:

- `handled`
- `clarification_required`
- `delegated_to_advanced_command`
- `unsupported`

The adapter is responsible for rendering these outcomes, not interpreting the business meaning behind them.

## Final Module Plan for Phase 2

New Phase 2 modules:

- `src/controller/contracts.py`
- `src/controller/intents.py`
- `src/controller/clarification.py`
- `src/controller/agent_controller.py`

Expected touched files:

- `src/main.py`
- optionally a new CLI adapter helper such as `src/cli/adapter.py`
- `src/cli/ui.py`
- `README.md`
- relevant docs under `docs/`

Legacy files to demote:

- command-first top-level flows in `src/main.py`
- product-facing reliance on `/task`
- product-facing reliance on `/operation`

## Final Implementation Order

Phase 2 coding order is fixed as:

1. implement controller contracts
2. implement intent definitions
3. implement clarification definitions
4. implement the Agent Controller
5. rewrite the CLI entry path to use the controller by default
6. rewrite help and onboarding content
7. demote legacy slash commands from the primary product path

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Testing Plan for Phase 2

Recommended new test files:

- `tests/test_controller_contracts.py`
- `tests/test_controller_intents.py`
- `tests/test_controller_clarification.py`
- `tests/test_agent_controller.py`

Required test areas:

### Contracts

- structured controller request creation
- structured controller result creation
- clarification payload round-trip behavior

### Intent Logic

- normal request classification
- redteam request classification
- record lookup classification
- advanced slash command classification
- ambiguous request detection

### Clarification Logic

- bare target clarification
- missing-target clarification
- persistent-vs-temporary clarification
- record-scope clarification

### Controller Integration

- controller + `SessionService` integration
- natural-language startup path
- advanced slash command fallback
- controller response rendering path through CLI

## Final Legacy Boundary

### REWRITE REQUIRED

The primary runtime entry path must not depend on:

- `/task` as the default startup path
- `/operation` as the default startup path
- ad hoc command routing in `src/main.py` as the product workflow owner

### Allowed Temporary Boundary

Allowed during migration:

- advanced slash command access
- debug use of legacy command groups
- temporary internal testing through old operator flows

Not allowed:

- documenting old command flows as the recommended main path
- routing new natural-language requests into legacy command flows as a hidden dependency

### Replacement Meaning in Phase 2

In Phase 2, replacement means:

- replaced as the main startup path
- replaced as the documented first-use flow
- replaced in top-level runtime routing

It does not yet guarantee:

- total physical deletion of legacy code
- total removal of every old operator command from the repository

## Phase 2 Ready-to-Implement Checklist

Phase 2 is now considered fully converged if the team accepts the following locked decisions:

- natural language is the default entry path
- slash commands are advanced/debug-only
- the controller package lives under `src/controller/`
- `src/controller/agent_controller.py` owns top-level routing
- `src/main.py` becomes a thin bootstrap and adapter orchestration layer
- intent categories are fixed
- clarification is a structured controller behavior
- the CLI is an adapter, not the runtime owner

This checklist is now the Phase 2 baseline.
