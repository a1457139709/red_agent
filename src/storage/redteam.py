from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_FAMILY = "red_code"
SCHEMA_VERSION = "3"
RUNTIME_FAMILY = "red_team"


REDTEAM_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations (
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
    last_error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);
CREATE INDEX IF NOT EXISTS idx_operations_updated_at ON operations(updated_at DESC);

CREATE TABLE IF NOT EXISTS scope_policies (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    allowed_hostnames_json TEXT NOT NULL,
    allowed_ips_json TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS memory_profiles (
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

CREATE TABLE IF NOT EXISTS memory_entries (
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
CREATE INDEX IF NOT EXISTS idx_memory_entries_operation_id ON memory_entries(operation_id);
CREATE INDEX IF NOT EXISTS idx_memory_entries_entry_type ON memory_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_memory_entries_source_ref ON memory_entries(source_ref);
CREATE INDEX IF NOT EXISTS idx_memory_entries_relevance_score ON memory_entries(relevance_score DESC);

CREATE TABLE IF NOT EXISTS memory_snapshots (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    snapshot_kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS planner_runs (
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
CREATE INDEX IF NOT EXISTS idx_planner_runs_operation_id ON planner_runs(operation_id);
CREATE INDEX IF NOT EXISTS idx_planner_runs_status ON planner_runs(status);
CREATE INDEX IF NOT EXISTS idx_planner_runs_created_at ON planner_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    worker_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    host_info_json TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
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
CREATE INDEX IF NOT EXISTS idx_jobs_operation_id ON jobs(operation_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id);
CREATE INDEX IF NOT EXISTS idx_jobs_target_ref ON jobs(target_ref);
CREATE INDEX IF NOT EXISTS idx_jobs_parent_job_id ON jobs(parent_job_id);

CREATE TABLE IF NOT EXISTS job_dependencies (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    depends_on_job_id TEXT NOT NULL,
    dependency_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    UNIQUE (job_id, depends_on_job_id)
);
CREATE INDEX IF NOT EXISTS idx_job_dependencies_job_id ON job_dependencies(job_id);
CREATE INDEX IF NOT EXISTS idx_job_dependencies_depends_on_job_id ON job_dependencies(depends_on_job_id);

CREATE TABLE IF NOT EXISTS evidence (
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
CREATE INDEX IF NOT EXISTS idx_evidence_operation_id ON evidence(operation_id);
CREATE INDEX IF NOT EXISTS idx_evidence_job_id ON evidence(job_id);
CREATE INDEX IF NOT EXISTS idx_evidence_target_ref ON evidence(target_ref);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence(evidence_type);

CREATE TABLE IF NOT EXISTS findings (
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
CREATE INDEX IF NOT EXISTS idx_findings_operation_id ON findings(operation_id);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_target_ref ON findings(target_ref);
CREATE INDEX IF NOT EXISTS idx_findings_dedupe_key ON findings(dedupe_key);

CREATE TABLE IF NOT EXISTS worker_leases (
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
CREATE INDEX IF NOT EXISTS idx_worker_leases_worker_id ON worker_leases(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_leases_lease_expires_at ON worker_leases(lease_expires_at);

CREATE TABLE IF NOT EXISTS job_events (
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
"""


class RedTeamStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        db_exists = self.db_path.exists()
        with self.connect() as connection:
            if not db_exists:
                connection.executescript(REDTEAM_SCHEMA)
                self._write_metadata(connection)
                connection.commit()
                return

            if not self._has_table(connection, "app_metadata"):
                raise ValueError(
                    "This workspace uses an incompatible runtime schema. "
                    "Initialize a fresh red-team workspace or remove the old database."
                )

            metadata = self._read_metadata(connection)
            if metadata.get("schema_family") != SCHEMA_FAMILY:
                raise ValueError("Unsupported schema family for red-team storage")
            if metadata.get("runtime_family") != RUNTIME_FAMILY:
                raise ValueError("Unsupported runtime family for red-team storage")
            if metadata.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("Unsupported schema version for red-team storage")
            connection.executescript(REDTEAM_SCHEMA)
            connection.commit()

    def _write_metadata(self, connection: sqlite3.Connection) -> None:
        connection.executemany(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            [
                ("schema_family", SCHEMA_FAMILY),
                ("schema_version", SCHEMA_VERSION),
                ("runtime_family", RUNTIME_FAMILY),
            ],
        )

    def _read_metadata(self, connection: sqlite3.Connection) -> dict[str, str]:
        rows = connection.execute("SELECT key, value FROM app_metadata").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def _has_table(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None
