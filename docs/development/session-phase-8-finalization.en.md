# Phase 8 Finalization: Web Adapter Readiness

## Purpose

This document closes the design loop for **Phase 8: Web Adapter Readiness**.

It converts the Phase 8 planning guidance into a fixed implementation baseline. After this document, Phase 8 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the position of Phase 8 as adapter readiness rather than full Web delivery
- the separation between shared runtime logic and adapter transport logic
- the replacement of CLI-only shell state with transport-neutral conversation context
- the extraction of controller-plus-execution orchestration from `src/main.py`
- the Web-side DTO and serialization boundary
- the use of a bidirectional interactive transport for live execution and confirmation
- the explicit-session resource access contract for browsing and reporting
- the rejection of Rich output as an API contract
- the rejection of Web-only runtime semantics

It should be read together with:

- [SPEC](F:\Project\AI\red_agent\docs\SPEC.md)
- [Session Target Architecture](F:\Project\AI\red_agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](F:\Project\AI\red_agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 7 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-7-finalization.en.md)
- [Phase 8 Implementation Checklist](F:\Project\AI\red_agent\docs\development\session-phase-8-implementation-checklist.en.md)

## Phase 8 Status

Phase 8 is now **architecturally converged**.

This means:

- the Web adapter boundary is settled
- the shared interaction orchestration boundary is settled
- the conversation state model is settled
- the stream and resource transport directions are settled
- coding can begin without reopening the core adapter design

## Current Implementation Note

As of April 25, 2026, Phase 8 should be treated as **design-complete but only partially implemented**.

Current repository state to assume:

- Web-facing interfaces or adapter contracts may exist
- the runtime may already expose part of the Phase 8 boundary
- a fully working Web adapter and real Web interaction flow are **not** yet complete

This document therefore freezes the target contract for the remaining implementation work. It does
not mean that Phase 8 has already been fully delivered in product terms.

## Replacement Position of Phase 8

Phase 8 is the point where the session-centric runtime becomes **adapter-ready for Web consumption** without changing the core product semantics.

After Phase 8:

- CLI remains a first-class adapter, but no longer owns the reusable interaction contract
- Web integration can be added above the same controller and app services
- current-session binding is no longer trapped inside CLI shell state
- execution progress and confirmation can be transported as structured events
- record retrieval, dashboard flows, and report generation can be exposed through deterministic Web contracts

Phase 8 does not own:

- the actual Web UI implementation
- a specific backend framework decision
- frontend state management choices
- authentication or multi-user runtime design
- a new business logic layer for Web-only behavior

## Final Decisions

## 1. Phase 8 Is Adapter Readiness, Not Full Web Delivery

Final decision:

- Phase 8 delivers the runtime-side Web adapter boundary only

Meaning:

- the repository becomes ready for a future Web UI
- but this phase does not require shipping browser views, pages, or frontend code

Not allowed:

- expanding Phase 8 into a framework-selection or UI-design project
- delaying the runtime extraction until a full frontend exists

## 2. Shared Runtime Logic Remains in Controller and Application Services

Final decision:

- Web must reuse the same `AgentController`, `ExecutionService`, `SessionService`, `SessionRecordQueryService`, `ReportFlowService`, and `DashboardService` path already used by CLI-oriented runtime flows

Meaning:

- the Web adapter is a transport layer above the existing session-centric core
- Web must not create parallel domain rules for session binding, reports, findings, or execution

Not allowed:

- direct repository-driven product flows in Web handlers
- Web-only business rules that bypass the shared app services

## 3. Conversation Context Replaces CLI-Only Shell State as the Shared Adapter Model

Final decision:

- the shared adapter state model is `ConversationContext`, not `ShellState`

Required fields:

- `conversation_id`
- `active_skill_name`
- `active_session_id`
- `active_session_public_id`
- `active_session_mode`
- `active_session_title`
- `active_session_target_summary`
- `pending_clarification`

Meaning:

- session persistence stays in the `session` domain
- conversation context is adapter-owned working state for current-turn routing and continuity

Not allowed:

- treating conversation context as a persisted replacement for `session`
- leaving current-session binding as CLI-only state

## 4. `src/main.py` No Longer Owns the Cross-Adapter Interaction Contract

Final decision:

- `src/main.py` becomes a CLI adapter and composition entrypoint only

Meaning:

- CLI prompt handling and CLI-only advanced command glue may remain there
- reusable controller request construction, session binding updates, and execution orchestration must move out

Not allowed:

- using `src/main.py` as the permanent home for controller-plus-execution orchestration
- duplicating its orchestration logic in a future Web server entrypoint

## 5. SessionInteractionService Is the Shared Interaction Orchestrator

Final decision:

- Phase 8 introduces one shared interaction orchestrator

Recommended location:

- `src/app/session_interaction_service.py`

Responsibilities:

- accept user input plus `ConversationContext`
- construct `ControllerRequest`
- call `AgentController`
- update conversation bindings
- route execution bridges through `ExecutionService`
- emit adapter-facing structured interaction results and execution events

Meaning:

- adapters become thin translators around one stable interaction service

## 6. Interaction Port Is the Adapter Boundary for Live Progress and Confirmation

Final decision:

- live interaction side effects must pass through one transport-neutral interaction port

Recommended location:

- `src/app/interaction_port.py`

Required capabilities:

- emit controller result notifications when needed
- emit execution progress events
- request and await confirmation decisions
- emit error or terminal interaction events where needed

Meaning:

- CLI can implement the port with direct presenter calls and terminal input
- Web can implement the port with structured event emission and a bidirectional response channel

## 7. Web Uses Two Transport Families

Final decision:

- Phase 8 freezes two Web transport families

### Interactive Family

Purpose:

- natural-language interaction
- clarification answers
- slash-command compatibility
- live execution progress
- confirmation requests and replies

Required capability:

- bidirectional message exchange

Reference transport:

- a WebSocket-grade channel

### Resource Family

Purpose:

- deterministic session browsing
- history, steps, artifacts, findings, and reports retrieval
- report generation or reuse
- dashboard retrieval

Required capability:

- request and response transport

Reference transport:

- HTTP-style resource endpoints

Meaning:

- the product keeps a clear distinction between interactive conversation flow and explicit resource browsing flow

## 8. Current-Session Binding Remains Conversation-First in Interactive Flows

Final decision:

- current-session-first behavior remains valid only inside adapter-owned conversation context

Rules:

- interactive messages without explicit scope resolve against the bound conversation session first
- interactive clarifications continue through the same conversation context
- deterministic resource endpoints require explicit session identifiers

Meaning:

- Web gets the same “current session” experience as CLI in interactive mode
- resource browsing stays explicit and easy to reason about

Not allowed:

- silently inferring `latest` session in explicit resource endpoints
- making browser-global process state the source of current-session truth

## 9. Clarification and Confirmation Stay Main-Flow Runtime States

Final decision:

- clarification-required and confirmation-required states remain part of the main runtime interaction flow

Meaning:

- the controller still owns clarification decisions
- risk policy and execution gating still own confirmation decisions
- only the transport changes between CLI and Web

Not allowed:

- re-implementing clarification logic in Web handlers
- re-implementing confirmation policy in Web handlers

## 10. Web Contracts Use Dedicated DTOs, Not Runtime Renderables

Final decision:

- Web payloads are explicit DTOs defined in `src/web/contracts.py`

Required serialized surfaces:

- conversation snapshot
- controller result payload
- record lookup payload
- finding explanation payload
- generated report payload
- dashboard payload
- execution event envelope
- confirmation request payload

Meaning:

- runtime dataclasses and model objects remain internal representations
- Rich output remains CLI-only rendering

Not allowed:

- serializing formatted presenter strings as the primary API
- treating Rich tables or CLI messages as stable Web schema

## 11. Execution Progress Is Streamed Through Ordered Event Envelopes

Final decision:

- all live interactive progress visible to Web must travel through ordered event envelopes

Required envelope fields:

- `conversation_id`
- `sequence`
- `event_kind`
- `session_id`
- `session_public_id`
- `timestamp`
- `payload`

Required event kinds:

- `controller_result`
- `clarification_required`
- `execution_progress`
- `confirmation_required`
- `confirmation_resolved`
- `final_answer`
- `interaction_error`

Meaning:

- clients can render deterministic progress
- event ordering is explicit instead of inferred from print timing

## 12. `ExecutionProgressEvent` Remains the Base Execution Progress Structure

Final decision:

- `ExecutionProgressEvent` remains the base runtime execution progress structure

Meaning:

- the Web layer wraps or serializes it
- the runtime does not create a second execution event model just for Web

Allowed:

- adding transport-neutral metadata if strictly needed for ordering or correlation

Not allowed:

- replacing execution events with Web-only event classes inside the runtime

## 13. Confirmation Must Be Awaitable Without `input()`

Final decision:

- the shared interaction contract must support awaiting a confirmation decision without hard-coding terminal input

Meaning:

- CLI can still use terminal prompts through its interaction-port implementation
- Web can await a confirmation response through the interactive channel or a confirmation submission endpoint

Not allowed:

- keeping `input()` or prompt string assembly as the only confirmation runtime contract

## 14. Deterministic Resource Endpoints Are Explicit-Session-Oriented

Final decision:

- Phase 8 resource browsing contracts are explicit-session-oriented

Recommended families:

- session summary
- history summary
- execution steps
- artifacts
- findings
- reports
- finding explanation
- report generation or reuse
- dashboard

Meaning:

- deterministic browsing endpoints do not depend on slash command parsing
- browsing endpoints map directly onto existing service-layer retrieval contracts

## 15. Report and Dashboard Flows Reuse Existing Services

Final decision:

- Web report generation or reuse must call `ReportFlowService`
- Web dashboard views must call `DashboardService`
- Web record browsing must call `SessionRecordQueryService` or a thin facade above it

Meaning:

- Phase 7 retrieval semantics carry forward unchanged
- the Web adapter does not invent a separate reporting or dashboard stack

## 16. No Framework Lock-In Is Allowed in Phase 8

Final decision:

- Phase 8 does not select FastAPI, Flask, Starlette, React, Vue, or any comparable stack

Meaning:

- the runtime-facing contract must stand on its own
- framework glue becomes a later adapter integration detail

Allowed:

- introducing a `src/web/` package with framework-neutral modules

Not allowed:

- making the shared runtime depend on one specific server framework
- adding a web dependency merely to define the adapter boundary

## 17. Rejected Designs

The following designs are rejected for Phase 8.

### Rejected: Reusing Rich Output as the Web Contract

Reason:

- presenter output is human-formatted and unstable as an API

### Rejected: Leaving Current Session Binding Inside `ShellState`

Reason:

- Web requires conversation-bound continuity that cannot depend on one CLI loop object

### Rejected: Duplicating Controller Glue in a Future Web Entry Point

Reason:

- this would recreate the same orchestration problem that currently lives in `src/main.py`

### Rejected: One-Way Streaming as the Only Interactive Transport

Reason:

- confirmation-required execution steps need bidirectional interaction

### Rejected: Web-Only Business Logic Paths

Reason:

- they would break the shared session-centric architecture and cause behavior drift between adapters

### Rejected: Silent `latest` Fallback in Explicit Resource Endpoints

Reason:

- explicit browsing flows must stay deterministic and auditable

## Final Module Plan for Phase 8

Modules to introduce:

- `src/models/conversation_context.py`
- `src/app/interaction_port.py`
- `src/app/session_interaction_service.py`
- `src/web/contracts.py`
- `src/web/serialization.py`
- `src/web/conversation_store.py`
- `src/web/interaction_adapter.py`

Modules to rewrite or extend:

- `src/main.py`
- `src/app/execution_service.py`
- `src/runtime/execution_events.py`
- `src/controller/contracts.py`

Modules to keep reusable without changing their core role:

- `src/controller/agent_controller.py`
- `src/app/session_service.py`
- `src/app/session_record_query_service.py`
- `src/app/report_flow_service.py`
- `src/app/dashboard_service.py`
- `src/cli/ui.py`

## Final Implementation Order

Implementation should proceed in this order:

1. add `ConversationContext`
2. add `InteractionPort`
3. add `SessionInteractionService`
4. rewire CLI through the shared interaction service
5. add Web DTO contracts and serializers
6. add the Web conversation store
7. add the Web interaction adapter boundary
8. tighten execution confirmation and event ordering through the interaction port
9. add explicit resource adapter flows for records, reports, and dashboard
10. complete regression and adapter contract tests

## Final Testing Plan for Phase 8

Required testing areas:

- conversation context lifecycle
- controller request and binding behavior through `SessionInteractionService`
- clarification continuation through shared conversation context
- report and record retrieval through explicit-session Web-facing serialization
- dashboard serialization through Web DTOs
- event envelope ordering and shape
- confirmation-required execution flow through the interaction port
- CLI regressions after extraction through existing controller and presenter tests

Minimum scenario coverage:

1. Start a normal session through the shared interaction layer and keep the conversation bound.
2. Start a redteam session through the shared interaction layer and receive live execution progress events.
3. Trigger a clarification-required flow, answer it on the next turn, and continue with the same conversation binding.
4. Trigger a confirmation-required execution step and resolve it through the interaction port.
5. Browse session history, steps, findings, reports, and dashboard data through deterministic serialized payloads.
6. Reuse an existing report through the same report-flow service path used by the CLI.
7. Confirm that CLI behavior still works after `src/main.py` is reduced to adapter logic.

## Final Legacy Boundary

After Phase 8:

- the reusable interaction contract must not live in `src/main.py`
- current-session binding must not be CLI-only
- Web must not invent parallel runtime services
- Rich presenter output must not become the browser contract

Still allowed after Phase 8:

- CLI as the primary shipped interface
- framework-specific Web bootstrap work in a later phase
- internal reuse of the same controller and service stack for both adapters

## Phase 8 Ready-to-Implement Checklist

Phase 8 is ready to implement when the team accepts the following fixed decisions:

- Web readiness means adapter extraction, not full UI delivery
- `ConversationContext` is the shared adapter state model
- `SessionInteractionService` is the shared interaction orchestrator
- `InteractionPort` is the live progress and confirmation boundary
- Web uses a bidirectional interactive transport plus explicit-session resource endpoints
- Web payloads are dedicated DTOs, not presenter output
- record, report, and dashboard flows reuse existing app services
- no framework lock-in is introduced in this phase
