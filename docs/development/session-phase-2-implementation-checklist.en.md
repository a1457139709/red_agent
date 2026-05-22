# RETIRED DOCUMENT

# Phase 2 Implementation Checklist: Controller-First CLI and Intent Flow

## Purpose

This document breaks down **Phase 2: Controller-First CLI and Intent Flow** into implementation-ready engineering tasks.

It is intended to answer:

- what must be built in Phase 2
- which modules should be introduced
- which existing modules must be rewritten or frozen
- how natural-language-first interaction should work
- in what order the work should be implemented

This checklist assumes Phase 1 has already converged around the `session` domain model.

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 1 Finalization](D:\Project\Python\Agent\docs\development\session-phase-1-finalization.en.md)

## Phase Goal

Move the product from command-driven top-level routing to **controller-driven, natural-language-first interaction**, while keeping CLI as the primary surface.

Phase 2 establishes the runtime entry boundary that later phases will build on.

## Scope of Phase 2

This phase covers:

- introduction of an Agent Controller layer
- separation between CLI adapter and product logic
- intent classification for normal vs redteam workflows
- clarification flow for incomplete user requests
- reduction of slash commands to advanced and debug paths
- controller-driven session startup behavior

This phase does **not** yet require:

- full foreground execution closure
- risk-based confirmation policy implementation
- module/skill unification
- the full four-layer persistent storage split
- Web UI implementation

## Non-Goals

Do not do the following in Phase 2:

- keep `src/main.py` as the permanent center of product workflow logic
- preserve slash commands as the primary user entry point
- implement controller logic as prompt-only behavior with no code boundary
- route new top-level flows through legacy `/task` or `/operation` paths
- postpone the CLI/runtime split by wrapping existing command handlers

## Rewrite Policy

### REWRITE REQUIRED

Phase 2 is a **runtime entry rewrite**, not a cosmetic CLI update.

The implementation should prefer:

- introducing a real controller boundary
- treating the CLI as an adapter
- moving intent, clarification, and routing logic out of `src/main.py`
- making natural language the default path

The implementation should avoid:

- growing the existing slash-command router
- treating natural language as a secondary convenience mode
- embedding controller behavior into the presentation layer

## Target Outcomes

By the end of Phase 2:

1. The runtime has an explicit Agent Controller layer.
2. The CLI acts as an adapter, not as the workflow owner.
3. Users can begin the primary flow through natural language.
4. The system can distinguish between:
   - normal requests
   - redteam requests
   - ambiguous requests that require clarification
5. Slash commands remain available only as advanced or debug surfaces.

## Module Strategy

## Modules to Introduce

These modules should be added in Phase 2.

### Controller Package

Recommended new package:

- `src/controller/`

Recommended initial files:

- `src/controller/agent_controller.py`
- `src/controller/intents.py`
- `src/controller/clarification.py`
- `src/controller/contracts.py`

### Responsibilities

#### `agent_controller.py`

Own the controller entry flow:

- receive user input from adapters
- classify intent
- decide whether clarification is required
- choose normal vs redteam mode
- create or reuse sessions through `SessionService`
- return structured controller outputs to the adapter

#### `intents.py`

Define:

- intent types
- mode selection rules
- request categories

#### `clarification.py`

Define:

- clarification request types
- minimal required follow-up questions
- clarification result structures

#### `contracts.py`

Define:

- request and response DTOs between adapter and controller
- controller result status types
- adapter-safe output payloads

## Existing Modules to Rewrite

### REWRITE REQUIRED: `src/main.py`

Decision:

- `src/main.py` must stop owning the primary product workflow

Action:

- keep only bootstrapping, shell wiring, and adapter orchestration
- move top-level natural-language routing out of it

### REWRITE REQUIRED: CLI command handling in `src/main.py`

Decision:

- command handlers must not remain the default product path

Action:

- preserve only advanced and debug routing
- route default user input through the controller

### REWRITE REQUIRED: `src/cli/ui.py`

Decision:

- presentation remains important, but it must not become the controller

Action:

- preserve rendering concerns
- keep it adapter-safe and controller-agnostic

### REWRITE REQUIRED: Help and Usage Model

Affected areas:

- top-level help output
- startup guidance
- CLI usage examples

Action:

- rewrite help content so natural language becomes the primary documented flow

## Existing Modules to Keep as Reuse Candidates

These should remain reusable but are not the core implementation targets of Phase 2.

- `src/app/session_service.py`
- `src/agent/loop.py`
- `src/agent/prompt.py`
- `src/agent/state.py`
- `src/tools/executor.py`
- `src/cli/ui.py` rendering primitives

Phase 2 may integrate with them, but should not overload them with controller responsibilities.

## File-Level Checklist

## 1. Add the Controller Contracts

Files:

- `src/controller/contracts.py`

Checklist:

- define `ControllerRequest`
- define `ControllerResult`
- define clarification result payloads
- define adapter-visible output shapes

Completion check:

- the CLI can speak to the controller through structured request/response objects

## 2. Add the Intent Model

Files:

- `src/controller/intents.py`

Checklist:

- define top-level intent categories
- define mode routing categories
- define ambiguity states
- define minimal target-related intent metadata

Completion check:

- the controller can represent a request without immediately executing it

## 3. Add the Clarification Model

Files:

- `src/controller/clarification.py`

Checklist:

- define when clarification is required
- define the minimum question set for common cases
- define how clarification responses are applied to controller state

Completion check:

- ambiguous requests do not fall through to raw execution

## 4. Add the Agent Controller

Files:

- `src/controller/agent_controller.py`

Checklist:

- accept natural-language input
- classify intent
- request clarification when needed
- resolve session mode
- create or locate sessions via `SessionService`
- return structured results to adapters

Completion check:

- the controller can drive the top-level runtime without relying on slash commands

## 5. Rework the CLI Entry Flow

Files:

- `src/main.py`
- optionally `src/cli/adapter.py` if a dedicated adapter file is introduced

Checklist:

- keep bootstrap and shell loop responsibilities only
- send natural-language input to the controller
- preserve slash commands as advanced/debug-only paths
- stop letting direct command handlers define the primary product workflow

Completion check:

- normal startup does not require slash command knowledge

## 6. Rework Help and Product Guidance

Files:

- `src/cli/ui.py`
- `README.md`
- relevant docs under `docs/`

Checklist:

- show natural-language examples first
- move slash commands to advanced help
- explain normal vs redteam mode behavior in user terms

Completion check:

- a new user can discover the primary flow without reading operator commands first

## 7. Freeze Legacy Top-Level Entry Paths

Files:

- `src/main.py`
- old command help sections
- development docs if needed

Checklist:

- mark `/task` and `/operation` as legacy or advanced-only during migration
- ensure new product flows are not routed through them
- prevent new features from being built on top of legacy top-level routing

Completion check:

- no new product-facing flow depends on old top-level commands

## Intent Checklist

Phase 2 should define the minimum top-level intent categories.

Recommended categories:

- `normal_request`
- `redteam_request`
- `record_lookup_request`
- `advanced_command_request`
- `clarification_required`
- `unsupported_request`

Recommended behavior:

- natural-language requests map to the first four
- slash commands map to `advanced_command_request`
- missing information maps to `clarification_required`

## Clarification Checklist

The controller should define minimal clarification rules for common ambiguous inputs.

### Case 1. Bare Target Input

Example:

- `look at example.com`

Minimum clarification goals:

- determine whether this is temporary or persistent
- determine whether the user wants normal or redteam behavior

### Case 2. Security-Flavored but Incomplete Request

Example:

- `scan this host`

Minimum clarification goals:

- identify the target
- decide whether this is a one-shot probe or a persistent redteam session

### Case 3. Persistent Redteam Request

Example:

- `start a recon session for example.com`

Minimum clarification goals:

- confirm enough context to create the redteam session cleanly

### Case 4. Record Retrieval Request

Example:

- `show me what you already did`

Minimum clarification goals:

- identify which session or most recent session is in scope

## Adapter Boundary Checklist

The CLI adapter should:

- read input
- send structured requests to the controller
- render structured responses

The CLI adapter should not:

- decide mode routing
- build sessions directly
- implement clarification policy itself
- classify top-level intent using ad hoc if/else chains inside `main.py`

## Migration Sequence

Work should be performed in this order.

### Step 1. Freeze the Controller Contract on Paper

Before coding:

- finalize controller responsibilities
- finalize intent categories
- finalize clarification result types
- finalize adapter/controller boundary

Reason:

- avoid spreading controller logic across CLI and services

### Step 2. Add `src/controller/contracts.py`

Reason:

- adapter and controller should integrate through stable types

### Step 3. Add `src/controller/intents.py`

Reason:

- intent classification must be explicit before controller behavior is implemented

### Step 4. Add `src/controller/clarification.py`

Reason:

- clarification should be a first-class runtime concern, not a side effect

### Step 5. Add `src/controller/agent_controller.py`

Reason:

- the controller becomes the new top-level runtime boundary

### Step 6. Rewrite the CLI Entry Path

Files:

- `src/main.py`
- optional new CLI adapter file

Reason:

- Phase 2 only becomes real once the shell delegates primary workflow control to the controller

### Step 7. Rewrite Help and Onboarding Copy

Reason:

- user-facing guidance must match the new runtime entry model

## Deletion and Deprecation Checklist

Phase 2 should not delete all old command paths immediately, but it must define the product-facing demotion.

### Demote from Primary Flow

- `/task`
- `/operation`
- `/job`
- `/planner`

These may remain reachable as advanced or debug paths during migration, but they must not define the primary product experience.

### Keep as Advanced/Debug Paths

- slash command inspection
- old operator workflows needed for temporary internal testing

### Not Allowed

- documenting legacy commands as the recommended first-use path
- routing new natural-language requests into the old command flows as a hidden implementation dependency

## Testing Checklist

## Unit Tests

Recommended new test files:

- `tests/test_controller_contracts.py`
- `tests/test_controller_intents.py`
- `tests/test_controller_clarification.py`
- `tests/test_agent_controller.py`

Recommended checks:

- intent classification
- clarification-required detection
- mode routing
- controller response construction

## Integration Tests

Recommended checks:

- controller + `SessionService` integration
- controller + CLI adapter integration
- natural-language request entry path
- advanced slash command fallback behavior

## Regression Protection

Add tests that ensure:

- the primary flow no longer depends on `/task`
- the primary flow no longer depends on `/operation`
- the CLI can route plain text input into the controller directly

## Phase 2 Exit Review

Phase 2 should be considered complete only if all questions below can be answered with "yes".

1. Does the runtime now have an explicit Agent Controller layer?
2. Is natural language the primary entry path?
3. Is the CLI now acting as an adapter instead of a workflow owner?
4. Can the system distinguish normal, redteam, and clarification-needed requests?
5. Are slash commands demoted to advanced/debug paths rather than the main product flow?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 2 are:

- `src/controller/contracts.py`
- `src/controller/intents.py`
- `src/controller/clarification.py`
- `src/controller/agent_controller.py`
- rewritten CLI entry flow in `src/main.py`
- updated help and onboarding text

If any of these are missing, Phase 2 is not yet complete as an architecture step.
