# Red-Team Agent Schema V2

## Purpose

This document defines the target persistence schema for the V2 red-team runtime.

It follows the same architectural rules defined in:

- [red-team-agent-architecture-v2.md](/D:/Project/Python/Agent/docs/red-team-agent-architecture-v2.md)

Compatibility with the current `Task` / `Run` / checkpoint schema is not a goal.
This schema is a clean reset for the new runtime.

## Design Rules

### 1. SQLite is the metadata system of record

SQLite should store:

- operations
- scope policies
- planner runs
- jobs
- findings
- evidence metadata
- memory
- worker leases and heartbeats

SQLite should not store large binary or text artifacts as the primary evidence payload.

### 2. Filesystem stores evidence artifacts

Large artifacts should be stored under managed operation directories.

Examples:

- response bodies
- screenshots
- raw scan outputs
- exported reports

### 3. Structured rows first, JSON second

Use explicit columns for query-critical fields.
Use JSON only for flexible secondary metadata.

### 4. Fail fast on schema mismatch

If the workspace has an older incompatible schema, startup should fail clearly.
Do not auto-upgrade or dual-read old runtime tables.

## Schema Versioning

Add an `app_metadata` table.

Required keys:

- `schema_family`
- `schema_version`
- `runtime_family`

Recommended initial values:

- `schema_family = red_code`
- `schema_version = 3`
- `runtime_family = red_team_v2`

Rationale:

- version `2` is already associated with the checkpoint redesign in current docs
- V2 runtime should use a visibly separate schema version to avoid ambiguity

## Core Tables

## 1. `operations`

Represents one operator objective.

```sql
CREATE TABLE operations (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL,
    planner_profile TEXT,
    memory_profile_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    FOREIGN KEY (memory_profile_id) REFERENCES memory_profiles(id)
);
```

Constraints:

- `status` must be one of:
  - `draft`
  - `ready`
  - `running`
  - `paused`
  - `blocked`
  - `failed`
  - `completed`
  - `cancelled`

Indexes:

```sql
CREATE INDEX idx_operations_status ON operations(status);
CREATE INDEX idx_operations_updated_at ON operations(updated_at DESC);
```

## 2. `scope_policies`

Stores hard runtime boundaries.

```sql
CREATE TABLE scope_policies (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    allowed_hosts_json TEXT NOT NULL,
    allowed_domains_json TEXT NOT NULL,
    allowed_cidrs_json TEXT NOT NULL,
    allowed_ports_json TEXT NOT NULL,
    allowed_protocols_json TEXT NOT NULL,
    denied_targets_json TEXT NOT NULL,
    allowed_tool_categories_json TEXT NOT NULL,
    max_concurrency INTEGER NOT NULL,
    requests_per_minute INTEGER,
    packets_per_second INTEGER,
    requires_confirmation_for_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);
```

Notes:

- `operation_id` is unique because one operation should have one active enforced policy
- if later policy history is needed, add a separate versioning table rather than weakening this rule

## 3. `planner_runs`

Stores model-driven planning passes.

```sql
CREATE TABLE planner_runs (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    operation_id TEXT NOT NULL,
    parent_planner_run_id TEXT,
    planner_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    decision_summary TEXT,
    memory_snapshot_id TEXT,
    created_job_count INTEGER NOT NULL DEFAULT 0,
    updated_job_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_planner_run_id) REFERENCES planner_runs(id),
    FOREIGN KEY (memory_snapshot_id) REFERENCES memory_snapshots(id)
);
```

Constraints:

- `status` must be one of:
  - `queued`
  - `running`
  - `completed`
  - `failed`
  - `cancelled`

Indexes:

```sql
CREATE INDEX idx_planner_runs_operation_id ON planner_runs(operation_id);
CREATE INDEX idx_planner_runs_status ON planner_runs(status);
CREATE INDEX idx_planner_runs_created_at ON planner_runs(created_at DESC);
```

## 4. `jobs`

The central execution unit.

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    operation_id TEXT NOT NULL,
    planner_run_id TEXT,
    parent_job_id TEXT,
    job_type TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    args_json TEXT NOT NULL,
    result_summary TEXT,
    timeout_seconds INTEGER NOT NULL,
    max_retries INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT,
    lease_expires_at TEXT,
    queued_at TEXT,
    started_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE,
    FOREIGN KEY (planner_run_id) REFERENCES planner_runs(id),
    FOREIGN KEY (parent_job_id) REFERENCES jobs(id),
    FOREIGN KEY (worker_id) REFERENCES workers(id)
);
```

Constraints:

- `status` must be one of:
  - `pending`
  - `queued`
  - `running`
  - `succeeded`
  - `failed`
  - `timed_out`
  - `cancelled`
  - `blocked`

Indexes:

```sql
CREATE INDEX idx_jobs_operation_id ON jobs(operation_id);
CREATE INDEX idx_jobs_status_priority ON jobs(status, priority, created_at);
CREATE INDEX idx_jobs_worker_id ON jobs(worker_id);
CREATE INDEX idx_jobs_target_ref ON jobs(target_ref);
CREATE INDEX idx_jobs_parent_job_id ON jobs(parent_job_id);
```

## 5. `job_dependencies`

Represents dependency edges.

```sql
CREATE TABLE job_dependencies (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    depends_on_job_id TEXT NOT NULL,
    dependency_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    UNIQUE (job_id, depends_on_job_id)
);
```

Recommended `dependency_kind` values:

- `success_required`
- `completion_required`

Indexes:

```sql
CREATE INDEX idx_job_dependencies_job_id ON job_dependencies(job_id);
CREATE INDEX idx_job_dependencies_depends_on_job_id ON job_dependencies(depends_on_job_id);
```

## 6. `evidence`

Stores metadata for proof artifacts.

```sql
CREATE TABLE evidence (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    target_ref TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    artifact_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    hash_digest TEXT NOT NULL,
    byte_size INTEGER,
    captured_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
```

Indexes:

```sql
CREATE INDEX idx_evidence_operation_id ON evidence(operation_id);
CREATE INDEX idx_evidence_job_id ON evidence(job_id);
CREATE INDEX idx_evidence_target_ref ON evidence(target_ref);
CREATE INDEX idx_evidence_type ON evidence(evidence_type);
```

## 7. `findings`

Stores candidate and confirmed results.

```sql
CREATE TABLE findings (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    source_job_id TEXT,
    finding_type TEXT NOT NULL,
    title TEXT NOT NULL,
    target_ref TEXT,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    impact TEXT,
    reproduction_notes TEXT,
    next_action TEXT,
    dedupe_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE,
    FOREIGN KEY (source_job_id) REFERENCES jobs(id)
);
```

Constraints:

- `severity` should be one of:
  - `info`
  - `low`
  - `medium`
  - `high`
  - `critical`
- `status` should be one of:
  - `open`
  - `confirmed`
  - `dismissed`
  - `duplicate`
  - `fixed`
- `confidence` should be between `0.0` and `1.0`

Indexes:

```sql
CREATE INDEX idx_findings_operation_id ON findings(operation_id);
CREATE INDEX idx_findings_status ON findings(status);
CREATE INDEX idx_findings_severity ON findings(severity);
CREATE INDEX idx_findings_target_ref ON findings(target_ref);
CREATE INDEX idx_findings_dedupe_key ON findings(dedupe_key);
```

## 8. `memory_profiles`

Stores long-lived memory rules.

```sql
CREATE TABLE memory_profiles (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    profile_kind TEXT NOT NULL,
    instruction_text TEXT NOT NULL,
    tool_preferences_json TEXT NOT NULL,
    reporting_preferences_json TEXT NOT NULL,
    retention_policy_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);
```

## 9. `memory_entries`

Stores reusable structured facts.

```sql
CREATE TABLE memory_entries (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    relevance_score REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);
```

Indexes:

```sql
CREATE INDEX idx_memory_entries_operation_id ON memory_entries(operation_id);
CREATE INDEX idx_memory_entries_entry_type ON memory_entries(entry_type);
CREATE INDEX idx_memory_entries_source_ref ON memory_entries(source_ref);
CREATE INDEX idx_memory_entries_relevance_score ON memory_entries(relevance_score DESC);
```

## 10. `memory_snapshots`

Stores planner-facing compact memory bundles.

```sql
CREATE TABLE memory_snapshots (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    snapshot_kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);
```

Why this exists:

- planners often need a stable compact context bundle
- storing it separately improves replay and planner-run inspection

## 11. `workers`

Stores active and recent worker processes.

```sql
CREATE TABLE workers (
    id TEXT PRIMARY KEY,
    worker_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    host_info_json TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
```

Recommended `status` values:

- `starting`
- `idle`
- `busy`
- `stale`
- `stopped`

## 12. `worker_leases`

Stores job claim records explicitly.

```sql
CREATE TABLE worker_leases (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    job_id TEXT NOT NULL UNIQUE,
    leased_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    released_at TEXT,
    release_reason TEXT,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
```

Indexes:

```sql
CREATE INDEX idx_worker_leases_worker_id ON worker_leases(worker_id);
CREATE INDEX idx_worker_leases_lease_expires_at ON worker_leases(lease_expires_at);
```

## 13. `job_events`

Stores high-signal lifecycle and policy events.

```sql
CREATE TABLE job_events (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    job_id TEXT,
    planner_run_id TEXT,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (planner_run_id) REFERENCES planner_runs(id) ON DELETE CASCADE
);
```

Recommended `level` values:

- `debug`
- `info`
- `warning`
- `error`

## Filesystem Layout

Recommended operation artifact layout:

```text
.red-code/
  agent-v2.db
  operations/
    <operation_id>/
      evidence/
        <evidence_id>_<slug>.json
        <evidence_id>_<slug>.txt
        <evidence_id>_<slug>.png
      planner/
        <planner_run_id>.json
      exports/
        findings-summary.md
        evidence-index.json
```

Rules:

- `artifact_path` in SQLite must be relative to `.red-code/`
- callers must never provide absolute artifact destinations
- evidence writes must be atomic when practical

## Query Patterns

The schema should support these primary queries efficiently.

### Operation dashboard

Needs:

- operation status
- recent planner runs
- active jobs
- open findings
- recent evidence

### Scheduler admission

Needs:

- queued jobs ordered by priority
- dependency status
- matching scope policy
- available workers

### Planner context build

Needs:

- operation policy memory
- relevant memory entries
- recent evidence summaries
- open findings

### Findings review

Needs:

- all findings for one operation
- grouped by severity or target
- jump to source evidence and source job

## JSON Field Guidance

JSON is acceptable only for flexible payloads such as:

- `args_json`
- `metadata_json`
- `tool_preferences_json`
- `reporting_preferences_json`
- `retention_policy_json`
- `content_json`
- `details_json`

Do not hide query-critical fields inside JSON when they need filtering, sorting, or integrity checks.

Bad examples:

- job status inside JSON
- target scope inside JSON-only storage
- finding severity inside JSON

## Deletion Policy

Deletion should be conservative.

### Cascading deletes are acceptable for:

- deleting an operation in development
- deleting its scope, jobs, findings, evidence metadata, memory, and events

### Cascading deletes are not enough for:

- artifact files on disk

Operation deletion must run a service-level cleanup step that removes managed artifact directories after metadata deletion succeeds.

## Breaking Change Policy

Startup behavior should be:

1. open the database
2. read `app_metadata`
3. verify `runtime_family = red_team_v2`
4. verify `schema_version = 3`
5. fail fast if mismatched

Recommended error message:

> This workspace uses an incompatible runtime schema. Initialize a fresh V2 workspace or remove the old database.

## Initial Migration Strategy

Because compatibility is not a goal, the preferred rollout is:

1. introduce a new database file:
   - `.red-code/agent-v2.db`
2. keep old runtime data untouched during development
3. point new commands only to the V2 database
4. remove the old database path after the old runtime is retired

This approach is cleaner than trying to retrofit the new schema into the old task database.

## Minimal First Cut

If implementation must be staged, start with these tables:

- `app_metadata`
- `operations`
- `scope_policies`
- `planner_runs`
- `jobs`
- `job_dependencies`
- `evidence`
- `findings`
- `memory_profiles`
- `memory_entries`
- `workers`
- `worker_leases`
- `job_events`

Add `memory_snapshots` as soon as planner replay becomes necessary.

## Final Recommendation

The V2 schema should optimize for:

- explicit operational boundaries
- strong scheduler semantics
- queryable findings and evidence
- planner memory that is structured instead of transcript-heavy

The schema should not attempt to preserve the shape of the current task runtime.
It should reflect the new runtime directly and unapologetically.
