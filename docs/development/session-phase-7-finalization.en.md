# Phase 7 Finalization: Record Retrieval and Report Flows

## Purpose

This document closes the design loop for **Phase 7: Record Retrieval and Report Flows**.

It converts the Phase 7 planning guidance into a fixed implementation baseline. After this document, Phase 7 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the command-first retrieval boundary for session-owned records
- the current-session-first scope rules for record and report requests
- the structured query contract shared by command parsing and future natural-language assistance
- the separation between low-level record location and higher-level record query services
- the explanation-trace contract from findings back to artifacts and execution records
- the controller-facing report generation flow
- the report-type baseline for Phase 7
- the rejection of code-expanded natural-language routing as the primary retrieval path
- the rejection of legacy task/operation-based retrieval as a primary path

It should be read together with:

- [SPEC](F:\Project\AI\red_agent\docs\SPEC.md)
- [Session Target Architecture](F:\Project\AI\red_agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](F:\Project\AI\red_agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 6 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-6-finalization.en.md)
- [Phase 7 Implementation Checklist](F:\Project\AI\red_agent\docs\development\session-phase-7-implementation-checklist.en.md)

## Phase 7 Status

Phase 7 is now **architecturally converged**.

This means:

- the query entry model is settled
- the report flow boundary is settled
- the controller-facing retrieval contract is settled
- the explanation traceability requirement is settled
- coding can begin without reopening the retrieval model

## Replacement Position of Phase 7

Phase 7 is the point where session-owned records become accessible through the main session-aware product query path in **retrieval architecture terms**.

After Phase 7:

- users can inspect prior execution records through fast session-bound commands
- controller record lookups no longer stop at locating a session
- reports become controller-accessible session outputs rather than export-only side effects
- natural-language assistance becomes an auxiliary translation layer rather than the primary routing path
- `TaskService` and `OperationService` are no longer allowed to power the primary retrieval and report flows

Phase 7 does not own:

- the physical storage ownership reset from Phase 6
- the future Web adapter from Phase 8
- reclassifying `memory` as a user-facing primary result layer
- direct sub-agent execution of runtime queries without main-agent validation

## Final Decisions

## 1. Command-First Retrieval Is the Primary Retrieval Path

Final decision:

- Phase 7 retrieval is driven primarily through session-aware query commands

Representative commands:

- `/status`
- `/history`
- `/steps`
- `/artifacts`
- `/findings`
- `/reports`
- `/show A0001`
- `/why F0001`
- `/report session_summary`

Meaning:

- the primary retrieval path must be deterministic and fast
- users should not need free-form natural-language classification for routine inspection
- the query surface should feel closer to operator tooling than to a conversational assistant

Not allowed:

- requiring natural language as the primary query input
- requiring users to know raw internal runtime entities before basic record lookup can succeed

## 2. Current Session Binding Is the Default Query Scope

Final decision:

- every Phase 7 record retrieval and report flow must resolve a session scope first

Default scope resolution order for command-first flows:

1. explicit scope from the request
2. current active session
3. clarification or explicit error if no active session exists

Supported explicit scope hints:

- `current`
- `latest`
- session public ID such as `S0001`

Rules:

- `latest` is supported only when explicitly requested
- command-first flows must not silently fall back to `latest`
- records remain session-owned even when artifact, finding, or report public IDs are used as lookup hints

## 3. Public IDs Remain Auxiliary, Not Primary

Final decision:

- public IDs remain available and supported, but they are not the primary user prerequisite for normal Phase 7 flows

Supported public ID families:

- sessions: `S0001`
- artifacts: `A0001`
- findings: `F0001`
- reports: `RP0001`

Rules:

- explicit public IDs may be used to resolve a request more precisely
- ordinary record lookup should default to the bound current session when possible
- controller responses may surface public IDs as stable references after resolution

## 4. Record Retrieval Targets

Final decision:

- Phase 7 retrieval covers exactly these main user-facing record targets

Targets:

- session history summary
- execution step logs and events
- artifacts
- findings
- reports

Meaning:

- `memory` remains AI-facing runtime support
- user-facing historical summaries may use memory-derived support internally
- but raw `memory` entries are not promoted to a primary analyst-facing result surface in Phase 7

## 5. Future Natural-Language Assistance Belongs to a Sub-Agent Layer

Final decision:

- natural-language assistance may remain as an auxiliary path, but it is not implemented as the primary code-routed retrieval path in Phase 7

Target direction:

- command parsing remains the primary Phase 7 entry
- any future natural-language assistant or sub-agent must translate free-form input into the same structured query contract used by commands
- the main agent validates and executes only structured requests

Not allowed:

- continuing to expand code-based natural-language heuristics as the main retrieval model
- allowing a future sub-agent to bypass the main agent and execute retrieval or report flows directly

## 6. SessionRecordLocator Remains a Low-Level Aggregator

Final decision:

- `SessionRecordLocator` remains the low-level Phase 6 session-owned record aggregator

Responsibilities retained:

- exact per-layer counts
- per-layer list operations
- low-level record location across session-owned stores

Not allowed:

- using `SessionRecordLocator` itself as the main operator-facing retrieval service
- pushing semantic interpretation, explanation composition, or controller-level response shaping into the locator

## 7. SessionRecordQueryService Is the Phase 7 Retrieval Service

Final decision:

- Phase 7 introduces a dedicated retrieval service above the locator layer

Recommended location:

- `src/app/session_record_query_service.py`

Responsibilities:

- organize session-owned records into controller-facing retrieval payloads
- provide session history summaries
- provide execution-step retrieval views
- provide filtered artifacts, findings, and reports
- produce explanation traces for findings

Minimum service surface:

```python
class SessionRecordQueryService:
    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SessionRecordQueryService": ...

    def get_history_summary(self, session_identifier: str, ...) -> ...: ...
    def list_execution_steps(self, session_identifier: str, limit: int | None = 50) -> ...: ...
    def list_artifacts(self, session_identifier: str, limit: int | None = 50, artifact_type: str | None = None) -> ...: ...
    def list_findings(self, session_identifier: str, limit: int | None = 50, severity: str | None = None, status: str | None = None) -> ...: ...
    def list_reports(self, session_identifier: str, limit: int | None = 50, report_type: str | None = None) -> ...: ...
    def explain_finding(self, session_identifier: str, finding_identifier: str) -> ...: ...
```

## 8. Finding Explanation Must Be Traceable

Final decision:

- `explain_finding(...)` must return a traceable explanation chain

Required explanation inputs:

- the finding itself
- linked artifacts
- source job, run, or event summary when available

Required behavior:

- the service must not invent unsupported rationale
- missing evidence or execution links must be reported explicitly as unavailable or incomplete

Not allowed:

- using generated prose to fill missing explanation evidence silently
- returning a confident finding explanation when the underlying trace is incomplete

## 9. Query Contracts Are Explicit and Structured

Final decision:

- controller contracts must represent Phase 7 record lookup intent with explicit structured query requests

Required kinds:

```text
RecordLookupKind
  - session_history
  - execution_steps
  - artifacts
  - findings
  - reports
  - finding_explanation
```

Required controller request and payload shapes:

- `RecordQueryRequest`
- `RecordLookupPayload`
- `FindingExplanationPayload`
- `GeneratedReportPayload`

Meaning:

- command parsing and any future natural-language sub-agent must converge on `RecordQueryRequest`
- `ControllerIntent.RECORD_LOOKUP_REQUEST` remains valid
- record lookup no longer ends at returning a `SessionSummary`

## 10. Agent Controller Owns the Retrieval Orchestration Path

Final decision:

- the record lookup branch in `AgentController` becomes a full retrieval orchestration path

Required flow:

1. parse or receive a structured record query
2. resolve session scope
3. invoke `SessionRecordQueryService` or `ReportFlowService`
4. return structured payloads through controller results

Not allowed:

- keeping record lookup as a session-only lookup shortcut
- bypassing the controller and requiring ad hoc CLI-only retrieval assembly

## 11. ReportFlowService Is the Phase 7 Report Orchestration Service

Final decision:

- Phase 7 introduces a dedicated report-flow service above the Phase 6 persistence-only report service

Recommended location:

- `src/app/report_flow_service.py`

Responsibilities:

- generate or reuse session summary reports
- generate or reuse findings summary reports
- generate or reuse operator-readable reports
- provide controller-facing access to report outputs

Minimum service surface:

```python
class ReportFlowService:
    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ReportFlowService": ...

    def get_or_create_session_summary(self, session_identifier: str, ...) -> ...: ...
    def get_or_create_findings_summary(self, session_identifier: str, ...) -> ...: ...
    def get_or_create_operator_report(self, session_identifier: str, ...) -> ...: ...
```

## 12. Report Types Frozen for Phase 7

Final decision:

- Phase 7 supports exactly three primary report flow types

Report types:

- `session_summary`
- `findings_summary`
- `operator_report`

Meaning:

- `session_summary` focuses on what was done and what records exist
- `findings_summary` focuses on structured findings and supporting artifacts
- `operator_report` provides a human-readable session output suitable for operator review

## 13. Report Reuse Before Regeneration

Final decision:

- controller-triggered report flows should attempt reuse before generating a new report

Default behavior:

- reuse the most recent acceptable report of the requested type for the session when possible
- generate a new report only when no acceptable report exists

Reason:

- it avoids unnecessary duplicate reports
- it preserves a stable session-facing report experience

Phase 7 does not require a complex freshness policy beyond a clear and deterministic reuse rule.

## 14. Operator Report Default Output

Final decision:

- `operator_report` defaults to operator-readable Markdown output

Rules:

- the main human-facing report body should be readable without runtime internals
- structured supporting context may remain in report metadata
- report persistence still routes through the Phase 6 `ReportService`

## 15. Runtime Summaries Remain Main-Agent-Owned

Final decision:

- any runtime summary that is fed back into ongoing execution remains main-agent-owned

Meaning:

- helper agents may draft summaries in the future
- but the main agent remains responsible for validating, storing, and acting on stage summaries

Reason:

- retrieval, report flow, and execution continuity must remain consistent with one authority over session state

## 16. ReportService Remains Persistence-Focused

Final decision:

- `ReportService` remains responsible for report persistence, linking, and output file ownership

Target boundary:

- `ReportService` is not the full controller-facing report-orchestration service
- Phase 7 report flow coordination belongs to `ReportFlowService`

Legacy boundary:

- any remaining `operation_identifier` support in `ReportService.create_report(...)` is migration-only
- it must not remain part of the Phase 7 primary report path

## 17. Legacy Retrieval Boundary

Final decision:

- Phase 7 primary retrieval and report flows must not depend on legacy top-level services

Not allowed:

- `TaskService` as a primary retrieval dependency
- `OperationService` as a primary retrieval dependency
- `/task` or `/operation` as the expected user path for record lookup
- `evidence_export.py` or old evidence/export terminology as the target architectural report path

Allowed during migration:

- internal bridges where still needed to finish Phase 6 to Phase 7 handoff
- repository-local compatibility helpers that do not define the primary product path

## 18. Rejected Designs

The following designs are explicitly rejected and should be discarded.

### Rejected: Natural-Language-First Query Routing as the Primary Phase 7 Path

Reason:

- the target Phase 7 experience must remain fast, deterministic, and strongly bound to the current session

### Rejected: Continued Growth of Code-Based Natural-Language Heuristics

Reason:

- future language assistance belongs in a sub-agent translation layer, not in ever-growing controller rules

### Rejected: Exposing Raw Memory as a Primary User Record Layer

Reason:

- Phase 7 retrieval should expose session results and explainable execution history, not AI harness internals

### Rejected: Record Lookup That Ends at Session Resolution Only

Reason:

- Phase 7 exists to retrieve records, not just to locate a session

### Rejected: Explanation by Guessing

Reason:

- explanations must remain traceable back to artifacts and execution records

### Rejected: Report Flows as Export-Only Helpers

Reason:

- reports must be controller-accessible session outputs

### Rejected: Primary Phase 7 Dependence on `TaskService` or `OperationService`

Reason:

- that would preserve the old top-level architecture in the main retrieval path

## Final Module Plan for Phase 7

New Phase 7 modules:

- `src/app/session_record_query_service.py`
- `src/app/report_flow_service.py`

Expected touched files:

- `src/app/session_record_locator.py`
- `src/app/report_service.py`
- `src/controller/contracts.py`
- `src/controller/agent_controller.py`
- `src/main.py`
- optionally `src/cli/ui.py`
- optionally limited compatibility code in `src/controller/intents.py`
- relevant docs under `docs/`

Existing services to integrate:

- `src/app/session_service.py`
- `src/app/run_service.py`
- `src/app/session_event_service.py`
- `src/app/artifact_service.py`
- `src/app/finding_service.py`
- `src/app/report_service.py`

Legacy files to demote further:

- `src/app/task_service.py`
- `src/app/operation_service.py`
- `src/reporting/evidence_export.py`

## Final Implementation Order

Phase 7 coding order is fixed as:

1. implement Phase 7 structured query models and controller contract updates
2. implement session-aware query command parsing
3. implement `SessionRecordQueryService`
4. implement finding explanation trace assembly
5. implement `ReportFlowService`
6. update `AgentController` query flow to return structured retrieval results
7. integrate command-triggered report flows
8. demote any remaining code-based natural-language query heuristics and legacy task/operation retrieval dependencies
9. add Phase 7 retrieval and report-flow tests

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Testing Plan for Phase 7

Recommended new test files:

- `tests/test_session_record_query_service.py`
- `tests/test_report_flow_service.py`
- `tests/test_controller_record_lookup.py`
- optionally `tests/test_query_command_parsing.py`
- optionally `tests/test_finding_explanation_trace.py`

Required test areas:

### Command Routing

- `/history` maps to `session_history`
- `/steps` maps to `execution_steps`
- `/artifacts` maps to artifact retrieval
- `/why F0001` maps to `finding_explanation`
- `/report session_summary` maps to controller-triggered report flow

### Scope Resolution

- current active session default
- explicit `latest`
- explicit `S0001`
- explicit artifact, finding, and report public IDs as lookup hints
- clarification or explicit error when no active session exists and no scope is given

### Retrieval Services

- history summaries aggregate session-owned records correctly
- execution step retrieval combines logs and events coherently
- artifact, finding, and report retrieval filters by session
- no primary dependency on `TaskService` or `OperationService`

### Explanation Traceability

- finding-to-artifact explanation paths remain traceable
- incomplete evidence returns explicit incomplete trace state
- no unsupported explanation text is generated as if it were evidence-backed

### Report Flows

- command-triggered session summary reports are reused or generated correctly
- findings summary reports derive from linked findings and artifacts
- operator reports produce human-readable Markdown output

## Final Legacy Boundary

Allowed during migration:

- low-level session-owned repositories and services from Phase 6
- temporary compatibility bridges inside persistence-focused report code
- limited compatibility handling for non-primary natural-language requests
- advanced/debug inspection commands while retrieval flows are stabilized

Not allowed:

- making `TaskService` the main record lookup path
- making `OperationService` the main record lookup path
- requiring natural-language classification for routine operator queries
- keeping `operation_identifier` as the target report-flow input
- documenting evidence/export as the target retrieval vocabulary

## Phase 7 Ready-to-Implement Checklist

Phase 7 is now considered fully converged if the team accepts the following locked decisions:

- Phase 7 retrieval is command-first and current-session-first
- every record and report flow resolves a session scope before execution
- public IDs remain supported but auxiliary
- `SessionRecordLocator` stays low-level and non-semantic
- `SessionRecordQueryService` is the target retrieval service
- future natural-language assistance must translate into the same structured query contract rather than become the primary code-routed path
- finding explanations must be traceable to artifacts and execution records
- controller contracts include structured query requests and structured retrieval payloads
- `ReportFlowService` is the target controller-facing report flow service
- report types are `session_summary`, `findings_summary`, and `operator_report`
- operator reports default to Markdown output
- runtime summaries remain main-agent-owned
- Phase 7 primary retrieval and report flows do not depend on `TaskService` or `OperationService`

This checklist is now the Phase 7 baseline.
