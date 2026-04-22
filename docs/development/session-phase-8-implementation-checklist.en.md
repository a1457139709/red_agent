# Phase 8 Implementation Checklist: Web Adapter Readiness

## Purpose

This document breaks down **Phase 8: Web Adapter Readiness** into implementation-ready engineering tasks.

It should be read together with:

- [SPEC](F:\Project\AI\red_agent\docs\SPEC.md)
- [Session Target Architecture](F:\Project\AI\red_agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](F:\Project\AI\red_agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 7 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-7-finalization.en.md)

This checklist assumes Phase 1 through Phase 7 have already established:

- `session` as the only top-level runtime work unit
- a controller-owned natural-language entry path
- foreground-first execution through the shared execution engine
- risk-based confirmation rules
- session-owned records, artifacts, findings, and reports
- command-first retrieval and report orchestration through shared services

## Phase Goal

Make the current session-centric runtime consumable from a future Web UI **without changing the core business model**, by extracting a transport-neutral interaction layer and defining a Web adapter contract above the existing controller and application services.

## Scope

Phase 8 covers:

- extracting adapter-neutral conversation state from CLI shell state
- extracting adapter-neutral interaction orchestration from `src/main.py`
- defining the Web-side DTO and serialization layer
- defining a Web conversation store for current-session binding and pending clarification state
- defining one bidirectional interactive transport contract for live execution and confirmation
- defining deterministic HTTP-style resource endpoints for session browsing, records, reports, and dashboard views
- ensuring execution progress and confirmation events can be emitted as structured Web stream events
- keeping the CLI on the same controller and service path after the extraction

Phase 8 does not require:

- building the actual Web frontend
- selecting a frontend framework
- introducing authentication or multi-user concerns
- replacing the CLI as the primary product surface
- moving business rules into transport handlers
- replacing command-first retrieval with Web-only query semantics

## Non-Goals

Do not do the following in Phase 8:

- add a separate Web-specific runtime model
- add Web-only business logic that bypasses `AgentController`, `ExecutionService`, or existing app services
- serialize Rich renderables directly as Web payloads
- treat `src/main.py` as the permanent orchestration center for both CLI and Web
- solve multi-user session isolation or browser auth in this phase
- lock the repository to FastAPI, Flask, React, or any other specific stack
- depend on direct repository access from Web handlers for normal product flows

## Rewrite Policy

### REWRITE REQUIRED

Phase 8 is an **adapter-boundary extraction**, not a rendering-only pass.

Current gaps after Phase 7:

- `src/main.py` still owns too much interaction orchestration
- `ShellState` is CLI-specific state, not adapter-neutral conversation state
- controller results are rendered directly to Rich presenter methods
- execution callbacks are shaped around synchronous CLI progress and prompt flows
- there is no stable Web-facing contract for conversation state, record payloads, or execution events

Target design:

- one shared interaction orchestration layer
- one transport-neutral conversation context model
- one CLI adapter using the shared interaction layer
- one Web adapter contract using the same controller and app services
- one structured event envelope for live execution updates
- one explicit serialization layer between runtime objects and Web payloads

Preferred implementation direction:

- extract conversation state out of `ShellState`
- extract controller-plus-execution orchestration out of `src/main.py`
- keep `AgentController` focused on intent and result construction
- keep `ExecutionService` focused on foreground execution and policy enforcement
- keep Web DTOs outside the controller and presenter modules

Avoid:

- teaching the controller about Web transport details
- rebuilding a second presenter abstraction inside the Web layer
- converting Rich output strings into a fake API contract
- leaving current-session binding as an implicit CLI-only behavior

## Target Outcomes

By the end of Phase 8:

1. CLI and future Web flows share one interaction orchestration path above the controller and execution service.
2. Adapter-owned conversation state is represented by one transport-neutral model instead of `ShellState`.
3. Web clients can maintain current-session binding, pending clarification, and confirmation context through a dedicated conversation store.
4. Live execution progress is representable as ordered structured events rather than CLI-only side effects.
5. Clarification-required and confirmation-required states are transportable without changing controller semantics.
6. Record retrieval, report generation, and dashboard views are available through deterministic Web-facing contracts that reuse existing services.
7. No framework choice is required to complete the runtime-facing part of Web readiness.
8. `src/main.py` becomes a CLI adapter rather than the long-term cross-adapter runtime hub.

## Web Adapter Contract

Phase 8 should freeze one Web adapter contract with two interaction families.

### 1. Interactive Conversation Transport

Primary use:

- natural-language session interaction
- clarification answers
- slash-command compatibility
- live execution progress
- confirmation requests and responses

Reference transport:

- one bidirectional conversation channel

Important rule:

- the runtime contract must remain transport-neutral, but the reference capability is **WebSocket-grade bidirectional interaction**

Reason:

- foreground execution may require mid-run confirmation
- one-way streaming alone is not enough for a faithful Web equivalent of the current CLI loop

### 2. Deterministic Resource Endpoints

Primary use:

- session browsing
- dashboard retrieval
- artifacts, findings, reports, and step history listing
- report generation or reuse by explicit session identifier

Important rule:

- direct resource endpoints should be explicit-session-oriented
- current-session-first behavior belongs to adapter-owned conversation context and interactive flows

## Conversation Context Direction

Phase 8 should replace the CLI-owned `ShellState` pattern with one shared conversation context model.

Recommended additions:

- `conversation_id`
- `active_skill_name`
- `active_session_id`
- `active_session_public_id`
- `active_session_mode`
- `active_session_title`
- `active_session_target_summary`
- `pending_clarification`

Recommended rules:

- CLI keeps one in-memory conversation context for the shell loop
- Web keeps one conversation context per browser conversation
- conversation context is adapter-owned UI state, not a persisted domain session
- persistent runtime ownership remains on `session`

## Interaction Service Direction

Phase 8 should introduce one shared interaction orchestration service above the controller layer.

Add:

- `src/app/session_interaction_service.py`

Responsibilities:

- accept raw user input plus current conversation context
- build `ControllerRequest`
- call `AgentController`
- update conversation bindings after controller results
- route execution bridges through `ExecutionService`
- emit structured interaction events through an adapter-provided port
- preserve clarification and confirmation semantics across adapters

Completion check:

- CLI and Web adapters can both drive normal session interaction without reimplementing controller-plus-execution glue logic

## Interaction Port Direction

Phase 8 should stop passing around purely CLI-shaped callbacks from `src/main.py`.

Recommended addition:

- `src/app/interaction_port.py`

Responsibilities:

- define adapter-facing progress emission
- define adapter-facing informational or error emission when still needed
- define adapter-facing confirmation request flow
- support asynchronous confirmation and event delivery

Important rules:

- the port is transport-neutral
- the CLI adapter may still implement it with direct presenter calls and synchronous input
- the Web adapter must implement it with structured event emission and bidirectional reply handling

## Presenter and Serialization Direction

Phase 8 should treat CLI rendering and Web serialization as separate adapter concerns.

Keep:

- `src/cli/ui.py` as the Rich presenter implementation

Add:

- `src/web/contracts.py`
- `src/web/serialization.py`

Rules:

- `CliPresenter` stays human-rendering-only
- `ControllerResult`, `SessionDashboard`, `Artifact`, `Finding`, `Report`, and `ExecutionProgressEvent` are runtime objects, not raw API payloads
- the Web adapter must convert runtime objects into DTOs explicitly
- Web payload shape must not depend on Rich tables, panels, or formatted strings

## Resource Endpoint Direction

Phase 8 should freeze deterministic resource-level operations for the Web adapter.

Recommended endpoint families:

- `POST /api/conversations`
- `POST /api/conversations/{conversation_id}/messages`
- `GET /api/conversations/{conversation_id}`
- `POST /api/conversations/{conversation_id}/confirmations`
- `GET /api/sessions/{session_identifier}`
- `GET /api/sessions/{session_identifier}/history`
- `GET /api/sessions/{session_identifier}/steps`
- `GET /api/sessions/{session_identifier}/artifacts`
- `GET /api/sessions/{session_identifier}/findings`
- `GET /api/sessions/{session_identifier}/reports`
- `GET /api/sessions/{session_identifier}/findings/{finding_identifier}/explanation`
- `POST /api/sessions/{session_identifier}/reports`
- `GET /api/sessions/{session_identifier}/dashboard`

Rules:

- interactive message submission is conversation-bound
- deterministic browsing endpoints are explicit-session-bound
- report generation or reuse through resource endpoints must call `ReportFlowService`
- dashboard endpoints must call `DashboardService`
- record endpoints must call `SessionRecordQueryService` or a thin facade above it

## Stream Event Direction

Phase 8 should freeze one ordered Web event envelope.

Recommended envelope fields:

- `conversation_id`
- `sequence`
- `event_kind`
- `session_id`
- `session_public_id`
- `timestamp`
- `payload`

Recommended event kinds:

- `controller_result`
- `clarification_required`
- `execution_progress`
- `confirmation_required`
- `confirmation_resolved`
- `final_answer`
- `interaction_error`

Rules:

- `execution_progress` payloads should be derived from `ExecutionProgressEvent`
- ordering must be stable within a conversation
- event consumers must not infer meaning from human-formatted text alone

## Confirmation Flow Direction

Phase 8 should define one Web-safe confirmation rule.

Final direction for implementation:

- confirmation requests are emitted as structured events through the interactive channel
- Web clients reply through the same conversation transport or a confirmation submission endpoint
- the interaction port must allow the runtime to await a user decision without hard-coding `input()`

This means Phase 8 should demote:

- direct `input()` coupling
- CLI-only prompt assembly as the confirmation runtime contract

## Module Strategy

## Modules to Introduce

### `src/models/conversation_context.py`

Responsibilities:

- hold adapter-owned current conversation state
- replace the cross-adapter role currently played by `ShellState`

Completion check:

- both CLI and Web adapters can store the same core interaction state fields

### `src/app/interaction_port.py`

Responsibilities:

- define a transport-neutral interface for event emission and confirmation handling

Completion check:

- `SessionInteractionService` and `ExecutionService` no longer need adapter-specific callback signatures from `src/main.py`

### `src/app/session_interaction_service.py`

Responsibilities:

- orchestrate controller request creation
- update conversation context
- route execution bridges
- surface structured interaction outcomes

Completion check:

- adapter code becomes thin request or transport handling

### `src/web/contracts.py`

Responsibilities:

- define Web DTOs for conversation snapshots, controller results, record payloads, reports, dashboard views, and stream envelopes

Completion check:

- the Web contract can be tested without importing Rich presenter code

### `src/web/serialization.py`

Responsibilities:

- serialize controller and service-layer runtime objects into Web DTOs

Completion check:

- Web responses do not depend on formatted CLI strings

### `src/web/conversation_store.py`

Responsibilities:

- keep adapter-owned conversation contexts keyed by `conversation_id`
- support current-session binding and pending clarification continuation

Completion check:

- a Web client can continue a conversation without relying on global process state

### `src/web/interaction_adapter.py`

Responsibilities:

- expose transport-neutral entry functions for interactive message handling, stream event emission, and confirmation submission

Completion check:

- a future framework integration only needs to bind transport IO to the adapter functions

## Existing Modules to Rewrite or Extend

### REWRITE REQUIRED: `src/main.py`

Current problem:

- `src/main.py` still owns request building, controller result rendering, shell state mutation, and execution-bridge glue

Action:

- demote it into the CLI composition and shell loop adapter
- route interaction through `SessionInteractionService`
- keep advanced command handling only where it is truly CLI-specific

Completion check:

- `src/main.py` no longer defines the permanent cross-adapter interaction contract

### REWRITE REQUIRED: CLI State Handling

Affected area:

- current `ShellState` usage in `src/main.py`

Action:

- replace the shared runtime role of `ShellState` with `ConversationContext`
- keep only prompt-label helpers or shell-specific convenience behavior in CLI-local code

Completion check:

- current-session binding semantics are no longer trapped inside one CLI-only dataclass

### EXTEND: `src/app/execution_service.py`

Current problem:

- execution progress and confirmation callbacks are shaped around CLI callbacks and synchronous input assumptions

Action:

- route execution interaction through `InteractionPort`
- support asynchronous confirmation handling
- keep risk policy and scope enforcement unchanged

Completion check:

- Web adapters can await confirmation without inventing Web-only execution logic

### EXTEND: `src/runtime/execution_events.py`

Action:

- keep `ExecutionProgressEvent` as the base execution progress structure
- extend only if additional transport-neutral metadata is required for stable Web event ordering

Completion check:

- Web stream envelopes can carry execution events without rewriting the execution model

### EXTEND: `src/controller/contracts.py`

Action:

- keep controller contracts runtime-focused
- add or adjust only transport-neutral fields that are genuinely missing for adapter reuse

Not allowed:

- adding Web DTO classes directly into controller contracts

### KEEP: `src/cli/ui.py`

Action:

- retain it as CLI presentation code
- stop treating it as a reusable adapter contract for non-CLI consumers

Completion check:

- Web responses are built from serializers, not Rich presenter output

## File-Level Checklist

## 1. Add Shared Conversation Context

Add:

- `src/models/conversation_context.py`

Tasks:

- define the transport-neutral conversation state model
- include active session binding fields and pending clarification
- provide helpers for binding or clearing active session data where useful

Done when:

- CLI shell and Web conversation store can use the same shared state object

## 2. Add Interaction Port Contract

Add:

- `src/app/interaction_port.py`

Tasks:

- define how adapters receive controller results, progress updates, and confirmation requests
- define one asynchronous confirmation path
- avoid direct CLI presenter dependencies in the contract

Done when:

- execution and interaction orchestration no longer require raw `input()` as the only confirmation mechanism

## 3. Add Session Interaction Service

Add:

- `src/app/session_interaction_service.py`

Tasks:

- move controller request construction out of `src/main.py`
- move session binding updates out of `src/main.py`
- route execution bridges through shared orchestration
- preserve Phase 7 query command compatibility

Done when:

- adapters become request translators instead of runtime coordinators

## 4. Rewrite CLI Adapter Around Shared Interaction Service

Rewrite:

- `src/main.py`

Tasks:

- replace direct controller-orchestration glue with `SessionInteractionService`
- keep shell prompt and advanced command routing as CLI-only concerns
- adapt CLI presenter calls through the interaction port implementation

Done when:

- the CLI remains fully functional but no longer defines the reusable runtime flow

## 5. Introduce Web DTOs and Serializers

Add:

- `src/web/contracts.py`
- `src/web/serialization.py`

Tasks:

- define DTOs for conversation snapshots
- define DTOs for controller result payloads
- define DTOs for record lookup, finding explanation, report generation, and dashboard payloads
- define stream envelopes and confirmation payloads
- serialize enums and dataclasses explicitly

Done when:

- runtime objects can be converted to Web-safe payloads with deterministic shapes

## 6. Add Web Conversation Store

Add:

- `src/web/conversation_store.py`

Tasks:

- store conversation contexts by `conversation_id`
- allow lookup, creation, update, and clear behavior
- preserve pending clarification between messages
- keep storage local and adapter-owned

Done when:

- a Web interaction does not depend on a single global shell state

## 7. Add Web Interaction Adapter Boundary

Add:

- `src/web/interaction_adapter.py`

Tasks:

- define message handling entrypoints for conversation messages
- define event emission hooks for the interactive channel
- define confirmation submission entrypoints
- keep framework glue out of the shared adapter logic

Done when:

- a concrete Web server only needs to connect transport events to this adapter layer

## 8. Define Explicit Resource Adapter Flows

Affected services:

- `SessionService`
- `SessionRecordQueryService`
- `ReportFlowService`
- `DashboardService`

Tasks:

- define explicit-session resource adapter calls for session summary, history, steps, artifacts, findings, reports, explanation, report generation, and dashboard views
- avoid using slash command parsing for deterministic resource endpoints

Done when:

- the Web layer can browse session-owned data without simulating CLI input

## 9. Tighten Confirmation and Stream Ordering

Affected areas:

- `src/app/execution_service.py`
- `src/runtime/execution_events.py`
- Web event envelope serialization

Tasks:

- ensure confirmation-required states become structured events
- ensure event ordering is deterministic per conversation
- ensure completion and failure states terminate the interactive stream cleanly

Done when:

- a Web client can render live execution state without inspecting raw logs

## 10. Add Adapter Contract and Regression Tests

Add tests:

- `tests/test_session_interaction_service.py`
- `tests/test_conversation_context.py`
- `tests/test_web_contracts.py`
- `tests/test_web_serialization.py`
- `tests/test_web_conversation_store.py`

Extend tests:

- `tests/test_agent_controller.py`
- `tests/test_execution_service.py`
- `tests/test_cli_ui.py`
- `tests/test_agent_controller.py` shell-loop coverage areas

Done when:

- the shared interaction contract is covered independently from CLI rendering

## Implementation Sequence

Recommended order:

1. add `ConversationContext`
2. add `InteractionPort`
3. add `SessionInteractionService`
4. rewire `src/main.py` to consume the shared interaction service
5. add Web DTOs and serializers
6. add Web conversation store
7. add Web interaction adapter boundary
8. add explicit-session resource adapter helpers
9. tighten confirmation and stream event sequencing
10. expand regression and contract tests

Important rule:

- do not start from a framework bootstrap
- start from transport-neutral contracts and shared orchestration first

## Testing Checklist

Required tests:

- normal session interaction still works through the CLI after extraction
- redteam session startup still produces foreground execution through the shared interaction layer
- active session binding survives multiple interaction turns through `ConversationContext`
- pending clarification survives multiple interaction turns through `ConversationContext`
- structured record query commands still resolve against the current bound session in interactive flows
- direct resource adapter calls return explicit-session results without slash-command parsing
- generated report and reused report payloads serialize deterministically
- dashboard payloads serialize without depending on Rich output
- execution progress events preserve order and session identity in stream envelopes
- confirmation-required flows can await a user decision through the interaction port
- the CLI interaction port still supports synchronous human use
- the Web interaction port can be tested with fake transports and scripted confirmation responses

## Phase 8 Exit Review

Before closing Phase 8, verify:

- the reusable interaction contract is no longer owned by `src/main.py`
- CLI rendering is still isolated inside `src/cli/ui.py`
- conversation state is adapter-owned, not confused with persisted `session`
- Web DTOs are explicit and tested
- record retrieval and dashboard flows reuse existing app services
- no framework lock-in has been introduced
- no Web-only business logic path bypasses the controller or app services

## Recommended Deliverable Set

The minimum Phase 8 deliverable set should include:

- shared conversation context model
- shared interaction orchestration service
- shared interaction port contract
- CLI rewiring onto the shared orchestration path
- Web DTO and serialization layer
- Web conversation store
- Web interaction adapter contract
- adapter contract and regression tests

Anything less leaves the runtime only partially Web-ready and keeps too much product flow trapped inside the CLI entrypoint.
