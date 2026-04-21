# Phase 7 Implementation Checklist: Record Retrieval and Report Flows

## Purpose

This document breaks down **Phase 7: Record Retrieval and Report Flows** into implementation-ready engineering tasks.

It should be read together with:

- [SPEC](F:\Project\AI\red_agent\docs\SPEC.md)
- [Session Target Architecture](F:\Project\AI\red_agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](F:\Project\AI\red_agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 6 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-6-finalization.en.md)
- [Phase 7 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-7-finalization.en.md)

This checklist assumes Phase 1 through Phase 6 have already established:

- `session` as the only target top-level work unit
- a controller boundary owned by the main agent
- foreground-first execution
- risk-based confirmation
- session-owned persistent storage for runs, logs, checkpoints, jobs, events, memory, artifacts, findings, and reports
- `SessionRecordLocator` as the low-level multi-layer lookup service

## Phase Goal

Make session-owned execution records, findings, and reports accessible through fast session-aware query commands, while keeping retrieval explainable, report generation session-centric, and future natural-language assistance optional and subordinate to structured query contracts.

## Scope

Phase 7 covers:

- session-aware query command parsing
- current-session-first scope resolution for retrieval flows
- structured query request and retrieval payload contracts
- session history summaries
- execution step retrieval
- artifact, finding, and report retrieval
- finding explanation traces
- command-triggered report generation and reuse flows
- additional demotion of legacy task/operation retrieval dependencies
- future-compatible structured hooks for natural-language sub-agent assistance

Phase 7 does not require:

- storage ownership migration from Phase 6
- Web UI implementation
- promoting raw `memory` to the main user-facing retrieval layer
- primary natural-language routing in controller code
- direct sub-agent execution of runtime queries
- permanent legacy compatibility around `operation_identifier`

## Non-Goals

Do not do the following in Phase 7:

- use `TaskService` as the main record lookup service
- use `OperationService` as the main record lookup service
- require `/task` or `/operation` commands for normal record lookup
- treat `SessionRecordLocator` as the only retrieval layer
- expose raw harness memory as the normal analyst-facing browsing surface
- generate finding explanations without evidence-backed trace links
- keep report generation as an export-only helper path
- continue expanding rule-based natural-language parsing as the main query experience

## Rewrite Policy

### REWRITE REQUIRED

Phase 7 is a **query and report-access reset**, not just a small controller polish pass.

Current gaps after Phase 6:

- session-owned records exist, but controller lookup may still stop at session resolution
- low-level record listing exists, but semantic retrieval assembly is incomplete
- report persistence exists, but controller-facing report orchestration is not the target-state path
- routine operator queries still risk drifting toward natural-language heuristics instead of fast deterministic commands

Target design:

- one command-first query path
- current-session-first scoping
- explicit structured query contracts
- traceable explanation flows
- command-triggered report generation and reuse
- optional future sub-agent translation into the same structured query format
- no primary dependency on legacy task/operation top-level services

Preferred implementation direction:

- add one deterministic command parser for record and report queries
- add one retrieval service above the locator layer
- add one report-flow service above the persistence-focused report service
- extend controller contracts for structured query requests and retrieval payloads
- keep natural-language support limited to compatibility or future sub-agent handoff

Avoid:

- embedding semantic retrieval logic in the CLI rendering layer
- bypassing the controller for normal report requests
- using generated text as a substitute for missing trace evidence

## Target Outcomes

By the end of Phase 7:

1. Users can query prior records quickly through session-aware commands.
2. Command queries default to the current active session unless an explicit scope is given.
3. Controller requests and responses use structured query contracts rather than ad hoc parsing results.
4. Findings can be explained through a traceable chain to artifacts and execution records.
5. Reports can be generated or reused directly through command-accessible controller flows.
6. `ReportService` remains persistence-focused while report orchestration moves higher.
7. Natural-language assistance is no longer a primary code-routing obligation for Phase 7.
8. Normal retrieval paths no longer depend on `TaskService` or `OperationService`.

## Query Entry Contract

Phase 7 should freeze one fast query command family.

Primary commands:

- `/status`
- `/history`
- `/steps`
- `/artifacts`
- `/findings`
- `/reports`
- `/show <public_id>`
- `/why <finding_public_id>`
- `/report <session_summary|findings_summary|operator_report>`

Optional short aliases:

- `/s`
- `/h`
- `/a`
- `/f`
- `/r`

Scope rules:

- no explicit scope means "current active session"
- `latest` is valid only when explicitly requested
- explicit `S0001` is valid
- `A0001`, `F0001`, and `RP0001` may be used as lookup hints for `show` and explanation flows
- if there is no active session and no explicit scope, controller must clarify or fail explicitly

## Retrieval Model Direction

Phase 7 should treat record lookup as three layers.

### Query Entry

Primary path:

- deterministic session-aware query commands

Future auxiliary path:

- natural-language translation through a sub-agent that emits the same structured query contract

### Low-Level Record Access

Keep:

- `src/app/session_record_locator.py`

Responsibilities:

- counts
- per-layer list access
- session-owned record location

### Retrieval Semantics

Add:

- `src/app/session_record_query_service.py`

Responsibilities:

- session history summary
- execution-step retrieval views
- artifact, finding, and report query responses
- finding explanation traces
- controller-ready structured payload assembly

### Report Orchestration

Add:

- `src/app/report_flow_service.py`

Responsibilities:

- report reuse decision
- report generation coordination
- controller-facing session summary, findings summary, and operator report flows

## Controller Contract Direction

Phase 7 controller contracts should explicitly represent query requests and outputs.

Recommended additions in `src/controller/contracts.py`:

- `RecordLookupKind`
- `RecordQueryRequest`
- `RecordLookupPayload`
- `FindingExplanationPayload`
- `GeneratedReportPayload`

Recommended behavior:

- command parsing produces `RecordQueryRequest`
- any future natural-language sub-agent must also produce `RecordQueryRequest`
- `ControllerIntent.RECORD_LOOKUP_REQUEST` remains the intent family
- controller result payloads represent actual retrieval outputs
- session summary remains available, but no longer the only record lookup result

## Module Strategy

## Modules to Introduce

### `src/app/session_record_query_service.py`

Responsibilities:

- provide history summaries
- provide execution-step views
- provide filtered artifacts, findings, and reports
- provide finding explanation traces

Completion check:

- controller code can ask one service for semantic record retrieval without reading repositories directly

### `src/app/report_flow_service.py`

Responsibilities:

- reuse or create session summary reports
- reuse or create findings summary reports
- reuse or create operator reports
- coordinate with `ReportService` for persistence

Completion check:

- controller code can request reports through one report-flow facade

## Existing Modules to Rewrite or Extend

### REWRITE REQUIRED: Controller Contracts

Affected files:

- `src/controller/contracts.py`

Action:

- add explicit query request models
- add structured retrieval payload types
- add structured report-generation payload types

### REWRITE REQUIRED: Query Command Parsing

Affected files:

- `src/main.py`
- optionally `src/cli/ui.py`
- optionally a dedicated command parsing helper if the command surface grows

Action:

- parse the primary query command family
- resolve explicit and implicit scope hints
- convert commands into `RecordQueryRequest`
- keep command parsing deterministic and session-aware

### REWRITE REQUIRED: Agent Controller Query Branch

Affected files:

- `src/controller/agent_controller.py`

Action:

- accept structured record query requests
- resolve scope
- call `SessionRecordQueryService` or `ReportFlowService`
- return structured retrieval payloads rather than session summary only

### REWRITE REQUIRED: Natural-Language Compatibility Boundary

Affected files:

- `src/controller/intents.py`
- optionally `src/controller/clarification.py`

Action:

- do not continue growing natural-language rules as the primary query path
- keep only limited compatibility or handoff points if still needed
- reserve future natural-language translation for a sub-agent path that emits structured queries

### REWRITE REQUIRED: Report Flow Boundary

Affected files:

- `src/app/report_service.py`
- optionally `src/reporting/findings_summary.py`
- optionally `src/reporting/evidence_export.py`

Action:

- keep `ReportService` focused on persistence and linking
- move report selection, reuse, and orchestration responsibilities into `ReportFlowService`
- avoid continuing `operation_identifier` as the target controller-facing input

### EXTEND: Session Record Locator Integration

Affected files:

- `src/app/session_record_locator.py`

Action:

- keep locator low-level
- expose only the low-level access points Phase 7 query service needs
- do not move semantic explanation logic into the locator

## File-Level Checklist

## 1. Add Structured Query Models and Controller Contracts

Files:

- `src/controller/contracts.py`

Checklist:

- define `RecordLookupKind`
- define `RecordQueryRequest`
- define `RecordLookupPayload`
- define `FindingExplanationPayload`
- define `GeneratedReportPayload`
- extend `ControllerResult` as needed for structured retrieval outputs

Completion check:

- controller requests and results can represent actual record and report flows without ad hoc dictionaries

## 2. Add Session-Aware Query Command Parsing

Files:

- `src/main.py`
- optionally `src/cli/ui.py`
- optionally a dedicated parser helper

Checklist:

- parse `/status`, `/history`, `/steps`, `/artifacts`, `/findings`, `/reports`
- parse `/show <public_id>`
- parse `/why <finding_public_id>`
- parse `/report <report_type>`
- support current-session default scope
- support explicit `latest` and `S0001`

Completion check:

- command input can be converted deterministically into `RecordQueryRequest`

## 3. Add Session Record Query Service

Files:

- `src/app/session_record_query_service.py`

Checklist:

- implement `from_settings(...)`
- implement `get_history_summary(...)`
- implement `list_execution_steps(...)`
- implement `list_artifacts(...)`
- implement `list_findings(...)`
- implement `list_reports(...)`
- implement `explain_finding(...)`

Completion check:

- one service can assemble controller-ready retrieval results from session-owned stores

## 4. Add Finding Explanation Trace Assembly

Files:

- `src/app/session_record_query_service.py`
- existing finding, artifact, run, job, and event service integrations as needed

Checklist:

- load finding by session
- load linked artifacts
- load source job/run/event summaries when available
- mark missing trace segments explicitly
- avoid unsupported explanation generation

Completion check:

- a finding explanation is backed by real records or explicitly marked incomplete

## 5. Add Report Flow Service

Files:

- `src/app/report_flow_service.py`

Checklist:

- implement `get_or_create_session_summary(...)`
- implement `get_or_create_findings_summary(...)`
- implement `get_or_create_operator_report(...)`
- reuse recent acceptable reports before generating a new one
- route persistence through `ReportService`

Completion check:

- controller-facing report access no longer needs to build report logic inline

## 6. Rewrite Agent Controller Query Flow

Files:

- `src/controller/agent_controller.py`

Checklist:

- accept structured query requests
- resolve session scope before retrieval
- map lookup kind to retrieval/report-flow service
- return structured payloads
- keep session summary binding behavior only where still useful

Completion check:

- record lookup no longer ends after session resolution

## 7. Tighten Natural-Language Compatibility

Files:

- `src/controller/intents.py`
- optionally `src/controller/clarification.py`

Checklist:

- stop expanding natural-language heuristics for routine record queries
- preserve only narrow compatibility if still needed
- reserve future natural-language support for a sub-agent translation path
- ensure any future translated request can enter through `RecordQueryRequest`

Completion check:

- Phase 7 no longer depends on growing code-based natural-language classification for query behavior

## 8. Tighten Report Service Boundary

Files:

- `src/app/report_service.py`

Checklist:

- keep `session_identifier` as the target-facing main input
- demote `operation_identifier` to migration-only if still present
- avoid putting controller-facing reuse or orchestration policy inside this service

Completion check:

- report persistence and report orchestration are clearly separated

## 9. Rewire Rendering Paths

Files:

- `src/main.py`
- optionally `src/cli/ui.py`

Checklist:

- display history, artifacts, findings, reports, and explanation results cleanly
- display generated report responses cleanly
- keep current session visible enough that command defaults are understandable

Completion check:

- the command-first path can expose Phase 7 retrieval behavior end to end

## 10. Demote Legacy Retrieval Paths

Files:

- `src/app/task_service.py`
- `src/app/operation_service.py`
- related docs/help output

Checklist:

- stop documenting legacy services as the normal way to retrieve records
- keep any legacy inspection only as debug or migration support if still needed

Completion check:

- Phase 7 retrieval no longer depends on old top-level architecture

## Implementation Sequence

Work should be performed in this order:

1. freeze the command-first retrieval and report-flow contracts
2. add structured query models
3. add session-aware query command parsing
4. add `SessionRecordQueryService`
5. add finding explanation trace assembly
6. add `ReportFlowService`
7. rewrite `AgentController` query orchestration
8. tighten natural-language compatibility boundaries
9. tighten `ReportService` to the persistence boundary
10. integrate rendering paths
11. demote remaining legacy task/operation retrieval dependencies

## Testing Checklist

Recommended new test files:

- `tests/test_session_record_query_service.py`
- `tests/test_report_flow_service.py`
- `tests/test_controller_record_lookup.py`
- optionally `tests/test_query_command_parsing.py`
- optionally `tests/test_finding_explanation_trace.py`

Required test areas:

- `/history`, `/steps`, `/artifacts`, `/findings`, and `/reports` command parsing
- `/show A0001` and `/why F0001` routing
- `/report session_summary` and `/report operator_report` routing
- current-session default scope
- explicit `latest`
- explicit `S0001`
- history summary aggregation from session-owned records
- execution-step retrieval composition from logs and events
- session filtering for artifacts, findings, and reports
- finding-to-artifact traceability
- incomplete explanation trace handling
- command-triggered report reuse vs generation
- operator report default Markdown output
- no primary retrieval dependency on `TaskService` or `OperationService`
- no expanding dependency on code-based natural-language classification for the main query path

## Phase 7 Exit Review

Phase 7 is complete only if all questions below can be answered with "yes".

1. Can a user inspect prior records quickly through session-aware commands?
2. Do routine queries default to the current active session rather than a hidden fallback?
3. Do controller requests and results carry structured query and retrieval payloads?
4. Can findings be explained through a traceable record chain?
5. Can controller flows reuse or generate reports directly from session-owned records?
6. Is `ReportService` now clearly persistence-focused rather than the full report orchestration path?
7. Is natural-language assistance no longer a primary code-routing requirement for Phase 7?
8. Are `TaskService` and `OperationService` no longer primary Phase 7 retrieval dependencies?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 7 are:

- `src/app/session_record_query_service.py`
- `src/app/report_flow_service.py`
- updated controller contracts for structured query requests and retrieval payloads
- session-aware query command parsing
- updated `AgentController` query orchestration
- tightened natural-language compatibility boundary
- tightened `ReportService` persistence boundary
- docs marking task/operation retrieval paths as non-target for Phase 7

If any of these are missing, Phase 7 is not yet complete as a retrieval architecture step.
