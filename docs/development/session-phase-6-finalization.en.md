# Phase 6 Finalization: Session Storage Split

## Purpose

This document closes the design loop for **Phase 6: Session Storage Split**.

It converts the Phase 6 planning guidance into a fixed implementation baseline. After this document, Phase 6 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the target four-layer persistent storage shape
- the session-owned storage root and path contract
- the session-owned metadata and blob split
- the `artifact` and `report` vocabulary as target terminology
- the `SessionEvent` replacement for operation-scoped event storage
- the physical migration boundary for `task` and `operation`
- the migration strategy for legacy task/runtime and operation/runtime data
- the rejection of unnecessary hybrid storage and dual-write designs

It should be read together with:

- [SPEC](F:\Project\AI\red_agent\docs\SPEC.md)
- [Session Target Architecture](F:\Project\AI\red_agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](F:\Project\AI\red_agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 5 Finalization](F:\Project\AI\red_agent\docs\development\session-phase-5-finalization.en.md)
- [Phase 6 Implementation Checklist](F:\Project\AI\red_agent\docs\development\session-phase-6-implementation-checklist.en.md)
- [Checkpoint Storage Redesign](F:\Project\AI\red_agent\docs\architecture\checkpoint-storage-evolution.md)

## Phase 6 Status

Phase 6 is now **architecturally converged**.

This means:

- the session-owned storage shape is settled
- the physical merge boundary for `task` and `operation` is settled
- the artifact/report terminology direction is settled
- the migration direction from legacy storage is settled
- coding can begin without reopening the storage ownership model

## Replacement Position of Phase 6

Phase 6 is the point where `task` and `operation` stop owning persistent runtime data in **storage architecture terms**.

After Phase 6:

- persistent red-team results live under `session`
- execution records live under `session`
- `artifact` replaces `evidence` as the target result term
- `report` replaces ad hoc export flows as the target human-output term
- `TaskService` and `OperationService` are no longer allowed to own the primary runtime storage path

Phase 6 does not own:

- natural-language record retrieval UX
- final report-query flows
- Web adapter work

Those are Phase 7 and Phase 8 concerns.

## Final Decisions

## 1. Four-Layer Persistent Session Shape

Final decision:

- persistent red-team session results are organized into exactly four logical layers

Layers:

- `memory`
- `artifacts`
- `findings`
- `reports`

Meaning:

- `memory` is AI-facing runtime memory and checkpoint support
- `artifacts` is raw execution output and evidence-origin payload storage
- `findings` is structured analyst-facing conclusion storage
- `reports` is exported human-facing output storage

Not allowed:

- collapsing all persistent results into one transcript-style store
- storing analyst-facing outputs only in `memory`
- keeping `task` and `operation` as parallel owners of these layers

## 2. Session-Owned Storage Root

Final decision:

- persistent session filesystem storage lives under:

```text
.red-code/
  sessions/
    <session_public_id>/
      memory/
      artifacts/
      findings/
      reports/
```

Directory rules:

- `<session_public_id>` is the stable `Session.public_id`, for example `S0001`
- layer directories are created lazily when first needed
- all persistent layer files must remain under the owning session directory
- callers may not provide absolute filesystem destinations for layer outputs

## 3. SQLite vs Filesystem Boundary

Final decision:

- SQLite remains the structured metadata and indexing layer
- filesystem remains the blob, payload, and export file layer

SQLite owns:

- identities
- public IDs
- lifecycle state
- foreign-key links
- list and lookup indexes
- timestamps
- structured summaries and metadata

Filesystem owns:

- checkpoint blobs
- artifact payload files
- exported report files
- optional layer-specific serialized support files

Not allowed:

- using SQLite as the only blob store for large artifact and checkpoint payloads
- storing all layer state only as loose files without indexed metadata

## 4. Memory Layer Contract

Final decision:

- the memory layer is session-owned and AI-facing only

Required responsibilities:

- checkpoint blob persistence
- harness memory entries
- compressed context support
- stable extracted session facts when needed by the harness

Target filesystem path rules:

- checkpoint blobs live under:

```text
.red-code/sessions/<session_public_id>/memory/checkpoints/YYYY/MM/chk_<checkpoint_id>.json.gz
```

SQLite table:

- `session_memory_entries`

Ownership:

- every memory entry belongs to `session_id`
- memory entries may reference `source_job_id`
- memory entries may not be the only storage location for analyst-facing artifact, finding, or report outputs

## 5. Artifact Layer Contract

Final decision:

- `artifact` is the canonical Phase 6 term for raw execution outputs and evidence-origin results

`Evidence` becomes:

- a legacy migration term
- not the target architecture vocabulary

Minimum `Artifact` shape:

```text
Artifact
  id: str
  public_id: str
  session_id: str
  source_job_id: str | None
  artifact_type: str
  target_ref: str
  title: str
  summary: str
  artifact_path: str | None
  content_type: str | None
  hash_digest: str | None
  captured_at: str
  metadata: dict[str, Any]
```

Public ID policy:

- artifacts use `A0001` format

Filesystem rules:

- artifact payload files live under `.red-code/sessions/<session_public_id>/artifacts/`
- artifact metadata rows always point to session-owned paths

## 6. Finding Layer Contract

Final decision:

- findings are session-owned structured conclusions

`Finding` ownership changes:

- from `operation_id`
- to `session_id`

Minimum finding rules:

- a finding belongs to exactly one session
- a finding may reference one source job
- a finding may link to zero or more artifacts
- a finding may be listed without loading raw artifact payloads

Public ID policy:

- findings keep `F0001` format

Link table:

- `finding_artifact_links`

Rule:

- finding-artifact links must not cross session boundaries

## 7. Report Layer Contract

Final decision:

- Phase 6 introduces `Report` as a first-class persistent model

Minimum `Report` shape:

```text
Report
  id: str
  public_id: str
  session_id: str
  report_type: str
  title: str
  summary: str
  artifact_path: str | None
  created_at: str
  metadata: dict[str, Any]
```

Public ID policy:

- reports use `RP0001` format

Link tables:

- `report_artifact_links`
- `report_finding_links`

Filesystem rules:

- exported report files live under `.red-code/sessions/<session_public_id>/reports/`
- report rows may reference one primary output file through `artifact_path`
- linked findings and artifacts remain separately queryable after report generation

## 8. Session-Owned Execution Records

Final decision:

- Phase 6 rewrites the persistent execution record model to be session-owned

Target metadata tables:

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

Ownership rule:

- all target runtime storage must key off `session_id`
- no new primary runtime table may require `task_id` or `operation_id`

## 9. SessionEvent Replaces OperationEvent

Final decision:

- `SessionEvent` is the target Phase 6 event model name

`OperationEvent` becomes:

- legacy naming
- not the target storage contract

Minimum `SessionEvent` responsibilities:

- confirmation-required, approved, and denied events
- execution started, succeeded, and failed events
- tool/category/target attribution
- structured payload storage
- session-level audit lookup

Session event rows:

- belong to exactly one session
- may reference one source job
- may not expose `operation` as the owning top-level runtime entity

## 10. Scope Policy Ownership

Final decision:

- scope policy remains a reusable internal model, but its persistent ownership moves to `session`

Meaning:

- Phase 6 does not delete scope policy behavior
- Phase 6 does remove `operation` as the owning top-level container for persistent scoped execution data

Not allowed:

- leaving scope policy persistence permanently keyed to `operation_id`
- requiring `OperationService` as the primary access path for session-owned execution storage

## 11. Legacy Naming Boundary

Final decision:

- `artifact` and `report` are the target product and architecture terms from Phase 6 onward

Legacy names:

- `evidence`
- `export`

Allowed during migration:

- read-only adapters
- migration helpers
- compatibility test fixtures while the new services are added

Not allowed:

- continuing `EvidenceService` as the target persistent result service
- continuing `EvidenceExportService` as the target report generation path
- documenting `evidence/export` as the target Phase 6 model

## 12. Migration Strategy

Final decision:

- Phase 6 uses **new-table migration**, not in-place table mutation and not long-lived dual-write

Required migration direction:

1. create the new session-owned tables
2. migrate legacy rows into the new tables
3. switch primary runtime writes to the new tables
4. demote legacy services to read-only or migration-only
5. delete legacy write paths once the primary runtime no longer depends on them

Migration sources:

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

Not allowed:

- keeping permanent dual-write between legacy and target tables
- extending old task/operation tables as the long-term Phase 6 solution

## 13. Task-to-Session Migration Rule

Final decision:

- every legacy task-owned runtime record migrates under a session

Rules:

- if a legacy task already references `session_id`, that session is reused
- if a legacy task has no session, create a synthetic `normal` session for migration
- migrated task runs, task logs, and checkpoints are re-owned by that session

Status mapping direction:

- task lifecycle must be mapped into the existing Phase 1 `SessionStatus` set
- migration may preserve original task-specific status text in metadata where needed

## 14. Operation-to-Session Migration Rule

Final decision:

- every legacy operation-owned runtime record migrates under a persistent red-team session

Rules:

- each legacy operation becomes or maps to one `redteam + persistent` session
- jobs, events, memory entries, artifacts, findings, and report-related outputs migrate under that session
- scope-policy ownership must be re-keyed to the migrated session

Preservation rule:

- public IDs, timestamps, and intra-record links must remain traceable after migration

## 15. Persistence Contract

## Session Runs

Target table:

- `session_runs`

Minimum fields:

- `id`
- `public_id`
- `session_id`
- `status`
- `started_at`
- `finished_at`
- `step_count`
- `last_usage`
- `effective_skill_name`
- `effective_visible_tools`
- `failure_kind`
- `last_error`

Public ID policy:

- runs keep `R0001` format

## Session Logs

Target table:

- `session_logs`

Minimum fields:

- `id`
- `session_id`
- `run_id`
- `level`
- `message`
- `payload`
- `created_at`

Rule:

- session logs replace task-owned log storage as the primary runtime log stream

## Session Checkpoints

Target table:

- `session_checkpoints`

Minimum fields:

- `id`
- `session_id`
- `run_id`
- `created_at`
- `storage_kind`
- `blob_path`
- `blob_encoding`
- `payload_size_bytes`
- `payload_digest`
- `history_message_count`
- `history_text_bytes`
- `has_compressed_summary`

Rule:

- checkpoint blobs move under the owning session `memory/` directory

## Session Jobs

Target table:

- `session_jobs`

Rule:

- jobs keep current durable execution semantics
- job ownership moves from `operation_id` to `session_id`

## Session Memory Entries

Target table:

- `session_memory_entries`

Rule:

- memory entries are keyed by `session_id`
- entry shape remains structured JSON metadata plus summary

## Artifacts

Target table:

- `artifacts`

Rule:

- this table replaces `evidence` as the target result index

## Findings

Target table:

- `findings`

Rule:

- the table name remains `findings`
- the owning foreign key is `session_id`, not `operation_id`

## Reports

Target table:

- `reports`

Rule:

- reports are indexed as first-class persistent results
- generated report files live under the session `reports/` directory

## 16. Session Record Locator Boundary

Final decision:

- Phase 6 introduces one aggregator service for session-owned record lookup

Recommended location:

- `src/app/session_record_locator.py`

Responsibilities:

- summarize per-layer counts
- list memory entries
- list artifacts
- list findings
- list reports
- list runs, checkpoints, jobs, and events
- provide one session-level lookup surface for future Phase 7 retrieval flows

Not allowed:

- making Phase 7 retrieval depend on `TaskService` or `OperationService`

## 17. Rejected Designs

The following designs are explicitly rejected and should be discarded.

### Rejected: In-Place Mutation of Old Tables Forever

Reason:

- it preserves legacy ownership instead of finishing the storage reset

### Rejected: Permanent Dual-Write

Reason:

- it prolongs ambiguity about the true owner of runtime data

### Rejected: Keep `Evidence` as the Target Result Model

Reason:

- Phase 6 needs one target vocabulary that aligns with the four-layer architecture

### Rejected: Report Generation as Ad Hoc Export-Only Logic

Reason:

- reports must become indexed persistent session results

### Rejected: Keep Checkpoints Under Task Ownership

Reason:

- it blocks the physical merge of legacy top-level containers

### Rejected: Keep Jobs and Events Under Operation Ownership

Reason:

- it leaves `operation` as a live top-level storage owner

## Final Module Plan for Phase 6

New Phase 6 modules:

- `src/models/artifact.py`
- `src/models/report.py`
- `src/models/session_event.py`
- `src/app/artifact_service.py`
- `src/app/report_service.py`
- `src/app/session_record_locator.py`
- session-owned storage repositories for runs, checkpoints, jobs, events, memory, artifacts, report links, and finding links

Expected touched files:

- `src/app/checkpoint_service.py`
- `src/app/run_service.py`
- `src/app/job_service.py`
- `src/app/memory_service.py`
- `src/app/finding_service.py`
- `src/app/execution_service.py`
- `src/app/dashboard_service.py`
- `src/app/evidence_pipeline_service.py`
- `src/reporting/evidence_export.py`
- `src/reporting/findings_summary.py`
- `src/main.py`
- relevant docs under `docs/`

Legacy files to freeze or demote:

- `src/app/task_service.py`
- `src/app/operation_service.py`
- `src/app/evidence_service.py`
- `src/app/operation_event_service.py`
- legacy task/operation repositories once migration is complete

## Final Implementation Order

Phase 6 coding order is fixed as:

1. add session-owned storage path helpers
2. add new session-owned models
3. add new session-owned repositories and schema initialization
4. add artifact and report services
5. rewrite checkpoint, run, job, memory, finding, and event services to use `session_id`
6. add session record locator
7. implement legacy-to-session migration utilities
8. rewire artifact pipeline and report generation to session-owned paths
9. switch primary runtime reads and writes to the new session-owned services
10. demote legacy task/operation/evidence services to read-only or migration-only

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Testing Plan for Phase 6

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

### Four-Layer Storage

- persistent red-team sessions store memory, artifacts, findings, and reports as distinct layers
- layer counts can be resolved from one session lookup surface
- AI memory is not mixed with analyst-facing outputs

### Session Ownership

- runs, checkpoints, jobs, memory entries, artifacts, findings, reports, and events can all be listed by `session_id`
- primary runtime services no longer require `task_id` or `operation_id`

### Migration

- task/runtime data migrates into session-owned records
- operation/runtime data migrates into session-owned records
- links remain valid after migration
- public IDs and timestamps stay traceable

### Artifact and Report Terminology

- `ArtifactService` replaces evidence as the target persistent result service
- `ReportService` replaces export-only report generation as the target persistent output path

### Legacy Boundary

- primary runtime writes do not go through `TaskService`
- primary runtime writes do not go through `OperationService`
- remaining legacy services are read-only or migration-only

## Final Legacy Boundary

Allowed during migration:

- legacy read-only inspection
- one-off migration helpers
- compatibility tests while target services are added
- advanced/debug commands that inspect old runtime rows temporarily

Not allowed:

- routing new primary runtime writes through `TaskService`
- routing new primary runtime writes through `OperationService`
- treating `EvidenceService` as the target artifact model
- treating export-only helpers as the target report model

## Phase 6 Ready-to-Implement Checklist

Phase 6 is now considered fully converged if the team accepts the following locked decisions:

- persistent red-team results are split into `memory`, `artifacts`, `findings`, and `reports`
- session filesystem storage lives under `.red-code/sessions/<session_public_id>/`
- SQLite remains the metadata/index layer and filesystem remains the blob/export layer
- `artifact` is the canonical Phase 6 result term
- `report` is the canonical Phase 6 human-output term
- `SessionEvent` replaces `OperationEvent` as the target event model
- checkpoints, runs, jobs, memory entries, findings, and events are all keyed by `session_id`
- Phase 6 uses new-table migration rather than long-lived in-place mutation or dual-write
- legacy task/runtime and operation/runtime data are migrated into session-owned storage
- primary runtime storage ownership moves to `session`, not `task` or `operation`
- remaining task/operation/evidence services are migration-only, read-only, or removed
- Phase 7 is unblocked to build retrieval and report-query flows on session-owned storage

This checklist is now the Phase 6 baseline.
