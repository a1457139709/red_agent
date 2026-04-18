# Phase 6 Implementation Checklist: Session Storage Split

## Purpose

This document breaks down **Phase 6: Session Storage Split** into implementation-ready engineering tasks.

It should be read together with:

- [SPEC](F:\Project\AI\red_agent\docs\SPEC.md)
- [Session Target Architecture](F:\Project\AI\red_agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](F:\Project\AI\red_agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 5 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-5-finalization.en.md)
- [Phase 6 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-6-finalization.en.md)

This checklist assumes Phase 1 through Phase 5 have already established:

- `session` as the only target top-level work unit
- controller-first natural-language entry
- foreground-first execution
- risk-based confirmation policy
- session-aware module invocation without `operation_id`

## Phase Goal

Move persistent runtime ownership from legacy `task` and `operation` containers into one session-owned storage model, while splitting persistent red-team results into:

- `memory`
- `artifacts`
- `findings`
- `reports`

## Scope

Phase 6 covers:

- session-owned storage path helpers
- session-owned metadata tables
- session-owned checkpoint, run, log, job, event, and memory storage
- artifact and report models and services
- finding ownership migration to `session_id`
- session record aggregation for later retrieval flows
- migration utilities from task/runtime and operation/runtime data
- demotion of legacy task/operation/evidence write paths

Phase 6 does not require:

- final natural-language query UX for records and reports
- final Web UI views
- distributed execution
- permanent support for dual-write or hybrid legacy ownership

## Non-Goals

Do not do the following in Phase 6:

- keep `task` as a permanent primary owner of checkpoints, runs, or logs
- keep `operation` as a permanent primary owner of jobs, events, memory, artifacts, or findings
- keep `evidence` as the target result vocabulary
- keep export-only helpers as the target report model
- implement long-lived dual-write between legacy and session-owned tables
- defer the storage ownership decision to Phase 7

## Rewrite Policy

### REWRITE REQUIRED

Phase 6 is a **storage ownership reset**, not a cosmetic rename pass.

Current coexistence problems:

- checkpoints, runs, and logs are task-owned
- jobs, events, memory, evidence, and findings are operation-owned
- report output is export-oriented rather than session-owned
- session exists as the target top-level model but is not yet the universal storage owner

Target design:

- `session` owns persistent runtime storage
- four logical result layers are explicit
- primary runtime services accept `session_identifier`
- `artifact` and `report` become the target terms

Preferred implementation direction:

- create new session-owned tables
- migrate legacy data into them
- switch primary runtime writes to the new tables
- demote legacy services to read-only or migration-only

Avoid:

- stretching old task or operation tables until they “behave enough like” session storage
- preserving dual-write as an indefinite runtime contract

## Target Outcomes

By the end of Phase 6:

1. Persistent red-team session data is organized into `memory`, `artifacts`, `findings`, and `reports`.
2. Checkpoints, runs, logs, jobs, events, and memory entries are session-owned.
3. Artifacts replace evidence as the target persistent raw-output model.
4. Reports become first-class indexed outputs rather than export-only side effects.
5. Findings are keyed by `session_id` and linked to artifacts.
6. One session-level lookup service can locate all storage layers and execution records.
7. Legacy task/runtime and operation/runtime storage is migrated into session-owned tables.
8. `TaskService`, `OperationService`, and `EvidenceService` are no longer valid primary write paths.

## Storage Layout Contract

Persistent session filesystem layout:

```text
.red-code/
  sessions/
    <session_id>/
      memory/
      artifacts/
      findings/
      reports/
```

Recommended concrete subpaths:

- checkpoint blobs:
  - `.red-code/sessions/<session_id>/memory/checkpoints/YYYY/MM/chk_<checkpoint_id>.json.gz`
- artifact payload files:
  - `.red-code/sessions/<session_id>/artifacts/...`
- report output files:
  - `.red-code/sessions/<session_id>/reports/...`

The `findings/` directory remains reserved as part of the session-owned layer contract even when findings are metadata-first in SQLite.

## Session-Owned Table Direction

Phase 6 should create these target tables:

- `session_runs`
- `session_logs`
- `session_checkpoints`
- `session_jobs`
- `session_events`
- `session_memory_entries`
- `artifacts`
- `findings`
- `finding_artifact_links`
- `reports`
- `report_artifact_links`
- `report_finding_links`

Migration sources are fixed as:

- `tasks`
- `runs`
- `checkpoints`
- `operations`
- `jobs`
- `operation_events`
- `memory_entries`
- `evidence`
- `findings`
- `finding_evidence_links`

## Module Strategy

## Modules to Introduce

### `src/models/artifact.py`

Responsibilities:

- define the session-owned artifact entity
- define artifact serialization
- define public ID behavior

Completion check:

- artifact rows can be created and listed without `operation_id`

### `src/models/report.py`

Responsibilities:

- define report identity and metadata
- define report type and output file reference
- define serialization helpers

Completion check:

- reports are first-class persistent results rather than ad hoc export metadata

### `src/models/session_event.py`

Responsibilities:

- replace operation-owned event identity
- define structured session-level audit event payloads

Completion check:

- event rows no longer expose `operation` as the owning top-level runtime entity

### `src/app/artifact_service.py`

Responsibilities:

- create artifact rows
- validate session and job ownership
- list and persist artifacts by session

Completion check:

- raw result storage no longer requires `EvidenceService`

### `src/app/report_service.py`

Responsibilities:

- create report rows
- persist exported report files under the session `reports/` layer
- link reports to findings and artifacts
- fail atomically so invalid links or output-write errors do not leave partial report state
- return structured failure details that can be shown to the user and later forwarded to AI remediation flows

Completion check:

- report generation no longer depends on export-only helpers as the primary path

### `src/app/session_record_locator.py`

Responsibilities:

- summarize per-layer counts
- list runs, checkpoints, jobs, events, memory entries, artifacts, findings, and reports
- provide one session-owned retrieval surface for later Phase 7 work
- use exact repository-backed count queries for summary totals instead of bounded list enumeration

Completion check:

- one service can locate all session-owned persistent layers and execution records

## Existing Modules to Rewrite

### REWRITE REQUIRED: Checkpoint Storage

Affected files:

- `src/models/checkpoint.py`
- `src/storage/checkpoints.py`
- `src/app/checkpoint_service.py`

Action:

- replace task-owned checkpoint storage with session-owned checkpoint storage
- move checkpoint blob paths under the session `memory/` layer
- change listing and lookup APIs to accept `session_identifier`

### REWRITE REQUIRED: Runs and Logs

Affected files:

- `src/models/run.py`
- `src/storage/runs.py`
- `src/app/run_service.py`

Action:

- replace task-owned runs and logs with session-owned runs and logs
- stop requiring `task_id` as the primary run key

### REWRITE REQUIRED: Jobs, Memory, and Events

Affected files:

- `src/models/job.py`
- `src/storage/repositories/jobs.py`
- `src/app/job_service.py`
- `src/models/memory.py`
- `src/storage/repositories/memory.py`
- `src/app/memory_service.py`
- `src/models/operation_event.py`
- `src/storage/repositories/operation_events.py`
- `src/app/operation_event_service.py`

Action:

- re-key ownership from `operation_id` to `session_id`
- replace operation event naming with session event naming

### REWRITE REQUIRED: Findings

Affected files:

- `src/models/finding.py`
- `src/storage/repositories/findings.py`
- `src/app/finding_service.py`
- `src/models/finding_evidence_link.py`
- `src/storage/repositories/finding_evidence_links.py`

Action:

- re-key findings from `operation_id` to `session_id`
- replace evidence links with artifact links
- ensure links cannot cross session boundaries

### REWRITE REQUIRED: Evidence and Export Paths

Affected files:

- `src/models/evidence.py`
- `src/storage/repositories/evidence.py`
- `src/app/evidence_service.py`
- `src/app/evidence_pipeline_service.py`
- `src/reporting/evidence_export.py`
- `src/reporting/findings_summary.py`

Action:

- stop treating evidence/export as target terms
- replace evidence with artifacts
- replace export-only report generation with session-owned report generation

### REWRITE REQUIRED: Main Runtime Read/Write Paths

Affected files:

- `src/app/execution_service.py`
- `src/app/dashboard_service.py`
- `src/main.py`

Action:

- remove new primary runtime dependencies on `task_id` and `operation_id`
- ensure runtime lookups and persistent result flows depend on session-owned services

## Existing Modules to Keep as Internal Reuse Candidates

These are not Phase 6 rewrite targets unless session ownership changes require interface adaptation:

- `src/orchestration/scope_validator.py`
- `src/app/confirmation_policy_service.py`
- `src/app/tool_access_policy_service.py`
- `src/runtime/foreground_runner.py`
- `src/tools/security/`

Phase 6 should reuse their behavior where practical, but not preserve legacy storage ownership through them.

## File-Level Checklist

## 1. Add Session Storage Path Helpers

Files:

- `src/agent/settings.py`
- optionally a new path helper module under `src/storage/` or `src/app/`

Checklist:

- add session storage root path helper
- add memory/artifacts/findings/reports path helpers
- ensure paths derive from the internal `session_id`
- ensure all paths remain under `.red-code/sessions/`

Completion check:

- services can derive deterministic session-owned filesystem paths without caller-supplied destinations

## 2. Add New Session-Owned Models

Files:

- `src/models/artifact.py`
- `src/models/report.py`
- `src/models/session_event.py`
- updates to `src/models/finding.py`
- updates to `src/models/run.py`
- updates to `src/models/checkpoint.py`
- updates to `src/models/job.py`
- updates to `src/models/memory.py`

Checklist:

- define session-owned identifiers
- define serialization helpers
- define public ID behavior where required
- ensure `Artifact` public IDs use the `A0001` family and repair any legacy `Exxxx` rows during repository initialization
- remove target-contract reliance on `task_id` and `operation_id`

Completion check:

- target runtime entities can all be represented without legacy top-level ownership

## 3. Add New Session-Owned Persistence Layer

Files:

- new repository modules under `src/storage/repositories/`
- schema initialization updates

Checklist:

- create the target tables listed in the Phase 6 finalization
- add required indexes for per-session lookup
- add foreign keys for session-owned linking
- keep SQLite as the metadata/index layer

Completion check:

- target session-owned records can be created, loaded, and listed independently of legacy top-level tables

## 4. Add Artifact and Report Services

Files:

- `src/app/artifact_service.py`
- `src/app/report_service.py`

Checklist:

- create artifacts by `session_identifier`
- create reports by `session_identifier`
- validate linked job, finding, and artifact ownership
- write report outputs into the session `reports/` directory

Completion check:

- raw result and report output storage no longer depends on legacy evidence/export services

## 5. Rewrite Checkpoint, Run, Job, Memory, Finding, and Event Services

Files:

- `src/app/checkpoint_service.py`
- `src/app/run_service.py`
- `src/app/job_service.py`
- `src/app/memory_service.py`
- `src/app/finding_service.py`
- `src/app/operation_event_service.py` or its replacement

Checklist:

- change primary inputs to `session_identifier`
- resolve `session_id` before persistence
- update list APIs to use session-owned repositories
- repair any pre-fix checkpoint blob paths into the owning session directory before serving checkpoint reads
- keep validation and status-transition behavior where still applicable

Completion check:

- primary service APIs no longer accept `task_id` or `operation_id` as their main runtime key

## 6. Add Session Record Locator

Files:

- `src/app/session_record_locator.py`

Checklist:

- implement `get_layer_summary(session_identifier)`
- add per-layer list helpers
- add execution-record list helpers
- back summary totals with exact count queries
- avoid dependency on `TaskService` and `OperationService`

Completion check:

- one service can locate the four layers and session-owned execution records

## 7. Add Migration Utilities

Files:

- recommended new migration helper under `src/app/` or `src/storage/migrations/`

Checklist:

- migrate legacy task-owned rows into session-owned rows
- migrate legacy operation-owned rows into session-owned rows
- preserve linkability of public IDs and timestamps
- reuse existing session references where available
- synthesize sessions for legacy task-owned data when no session exists

Completion check:

- legacy runtime data can be transferred into target tables without losing traceability

## 8. Rewrite Artifact Pipeline and Report Generation

Files:

- `src/app/evidence_pipeline_service.py`
- `src/reporting/evidence_export.py`
- `src/reporting/findings_summary.py`
- optionally new session-oriented reporting helpers

Checklist:

- write artifact payloads under session-owned artifact paths
- generate reports through `ReportService`
- link generated reports to artifacts and findings
- stop treating export directories as the primary persistent contract

Completion check:

- runtime artifact and report flows are session-owned end to end

## 9. Rewire Runtime Entry Points

Files:

- `src/app/execution_service.py`
- `src/app/dashboard_service.py`
- `src/main.py`

Checklist:

- remove temporary `session.id as operation_id` semantics from primary storage paths
- list and inspect persistent red-team outputs through session-owned services
- ensure future CLI queries do not require `/task` or `/operation` as the target contract

Completion check:

- persistent red-team output flows are routed through session-owned services

## 10. Demote Legacy Top-Level Services

Files:

- `src/app/task_service.py`
- `src/app/operation_service.py`
- `src/app/evidence_service.py`
- legacy repositories and related docs

Checklist:

- mark legacy write paths as deprecated or migration-only
- keep read-only inspection only where still needed temporarily
- stop extending them for new product-facing flows

Completion check:

- the team can clearly tell that legacy services are no longer the target write path

## Migration Sequence

Work should be performed in this order:

1. freeze the session-owned storage contract
2. add session-owned path helpers
3. add session-owned models
4. add session-owned repositories and schema updates
5. add artifact and report services
6. rewrite checkpoint, run, job, memory, finding, and event services
7. add session record locator
8. implement migration utilities
9. rewrite artifact pipeline and report generation
10. switch primary runtime reads and writes to the new session-owned services
11. demote legacy task/operation/evidence services

## Testing Checklist

Recommended new test files:

- `tests/test_artifact_repository.py`
- `tests/test_artifact_service.py`
- `tests/test_report_repository.py`
- `tests/test_report_service.py`
- `tests/test_session_record_locator.py`
- `tests/test_session_storage_migration.py`
- `tests/test_session_checkpoint_repository.py`
- `tests/test_session_run_repository.py`
- `tests/test_session_job_repository.py`
- `tests/test_session_event_repository.py`

Required test areas:

- session-owned path generation
- artifact create/get/list/update round-trip
- report create/get/list/update round-trip
- finding-artifact link integrity
- report-artifact and report-finding link integrity
- checkpoint/run/job/event lookup by `session_id`
- memory entry lookup by `session_id`
- migration from task/runtime data
- migration from operation/runtime data
- preservation of public IDs and timestamps
- report and artifact file path confinement under session directories
- primary service APIs rejecting target reliance on `task_id` and `operation_id`

## Phase 6 Exit Review

Phase 6 is complete only if all questions below can be answered with "yes".

1. Do persistent red-team sessions now store results in distinct `memory`, `artifacts`, `findings`, and `reports` layers?
2. Are checkpoints, runs, logs, jobs, events, and memory entries all session-owned?
3. Is `artifact` now the target raw-result model instead of `evidence`?
4. Is `report` now a first-class persistent result model?
5. Can one session-level lookup service locate all layers and execution records?
6. Can legacy task/runtime and operation/runtime data be migrated into session-owned storage?
7. Are `TaskService`, `OperationService`, and `EvidenceService` no longer valid primary write paths?
8. Is Phase 7 unblocked from building retrieval and report-query flows on top of session-owned storage?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 6 are:

- session-owned storage path helpers
- session-owned repositories for runs, checkpoints, jobs, events, and memory
- `src/models/artifact.py`
- `src/models/report.py`
- `src/models/session_event.py`
- `src/app/artifact_service.py`
- `src/app/report_service.py`
- `src/app/session_record_locator.py`
- rewritten session-owned checkpoint/run/job/memory/finding/event services
- migration utilities from legacy task/runtime and operation/runtime data
- rewritten session-owned artifact and report generation flows
- docs marking legacy task/operation/evidence services as non-target write paths

If any of these are missing, Phase 6 is not yet complete as a storage architecture step.
