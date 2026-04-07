from __future__ import annotations

import sqlite3
from typing import Iterable

from models.job import Job, JobLogEntry, JobStatus
from models.operation import OperationStatus
from storage.sqlite import SQLiteStorage

from ._common import allocate_public_id, get_row_by_identifier


JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    operation_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}',
    dependency_job_ids TEXT NOT NULL DEFAULT '[]',
    timeout_seconds INTEGER,
    retry_limit INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    queued_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    last_error TEXT,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    last_heartbeat_at TEXT,
    cancel_requested_at TEXT,
    cancel_reason TEXT,
    retry_after TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_public_id ON jobs(public_id);
CREATE INDEX IF NOT EXISTS idx_jobs_operation_updated_at ON jobs(operation_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(status, retry_after, queued_at, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_lease_expires_at ON jobs(status, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_jobs_cancel_requested_at ON jobs(status, cancel_requested_at);

CREATE TABLE IF NOT EXISTS job_logs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_job_logs_job_created_at ON job_logs(job_id, created_at DESC);
"""

JOB_RUNTIME_COLUMNS: dict[str, str] = {
    "lease_owner": "TEXT",
    "lease_token": "TEXT",
    "lease_expires_at": "TEXT",
    "last_heartbeat_at": "TEXT",
    "cancel_requested_at": "TEXT",
    "cancel_reason": "TEXT",
    "retry_after": "TEXT",
}


class JobRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, job: Job) -> Job:
        with self.storage.connect() as connection:
            self._create_with_connection(connection, job)
            connection.commit()
        return job

    def get(self, identifier: str) -> Job | None:
        with self.storage.connect() as connection:
            row = get_row_by_identifier(
                connection,
                table_name="jobs",
                identifier=identifier,
                order_column="updated_at",
            )
        return Job.from_row(dict(row)) if row else None

    def list(
        self,
        operation_id: str,
        *,
        status: JobStatus | None = None,
        limit: int | None = 50,
    ) -> list[Job]:
        query = "SELECT * FROM jobs WHERE operation_id = ?"
        params: list[object] = [operation_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Job.from_row(dict(row)) for row in rows]

    def list_by_statuses(
        self,
        statuses: Iterable[JobStatus],
        *,
        limit: int | None = None,
    ) -> list[Job]:
        normalized_statuses = [status.value for status in statuses]
        if not normalized_statuses:
            return []
        placeholders = ", ".join("?" for _ in normalized_statuses)
        query = f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY updated_at DESC"
        params: list[object] = list(normalized_statuses)
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Job.from_row(dict(row)) for row in rows]

    def update(self, job: Job) -> Job:
        with self.storage.connect() as connection:
            self._update_with_connection(connection, job)
            connection.commit()
        return job

    def create_log_entry(self, entry: JobLogEntry) -> JobLogEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO job_logs (
                    id, job_id, level, message, payload, created_at
                ) VALUES (
                    :id, :job_id, :level, :message, :payload, :created_at
                )
                """,
                entry.to_row(),
            )
            connection.commit()
        return entry

    def list_logs(self, job_id: str, *, limit: int = 20) -> list[JobLogEntry]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM job_logs
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        return [JobLogEntry.from_row(dict(row)) for row in rows]

    def count_running(self, operation_id: str, *, exclude_job_id: str | None = None) -> int:
        query = """
            SELECT COUNT(*) AS count
            FROM jobs
            WHERE operation_id = ? AND status = ?
        """
        params: list[object] = [operation_id, JobStatus.RUNNING.value]
        if exclude_job_id is not None:
            query += " AND id != ?"
            params.append(exclude_job_id)
        with self.storage.connect() as connection:
            row = connection.execute(
                query,
                params,
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def list_stale_leases(
        self,
        *,
        now: str,
        operation_id: str | None = None,
    ) -> list[Job]:
        query = """
            SELECT *
            FROM jobs
            WHERE status = ?
              AND (
                lease_expires_at IS NULL
                OR lease_expires_at <= ?
              )
        """
        params: list[object] = [JobStatus.RUNNING.value, now]
        if operation_id is not None:
            query += " AND operation_id = ?"
            params.append(operation_id)
        query += " ORDER BY lease_expires_at ASC, updated_at ASC"
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Job.from_row(dict(row)) for row in rows]

    def claim_next_queued_job(
        self,
        *,
        worker_id: str,
        lease_token: str,
        now: str,
        lease_expires_at: str,
    ) -> Job | None:
        with self.storage.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT jobs.id
                FROM jobs
                INNER JOIN operations ON operations.id = jobs.operation_id
                WHERE jobs.status = ?
                  AND (jobs.retry_after IS NULL OR jobs.retry_after <= ?)
                  AND operations.status IN (?, ?)
                ORDER BY jobs.queued_at ASC, jobs.created_at ASC, jobs.id ASC
                LIMIT 1
                """,
                (
                    JobStatus.QUEUED.value,
                    now,
                    OperationStatus.READY.value,
                    OperationStatus.RUNNING.value,
                ),
            ).fetchone()
            if row is None:
                connection.commit()
                return None

            updated = connection.execute(
                """
                UPDATE jobs
                SET
                    status = ?,
                    lease_owner = ?,
                    lease_token = ?,
                    lease_expires_at = ?,
                    last_heartbeat_at = ?,
                    started_at = COALESCE(started_at, ?),
                    finished_at = NULL,
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    worker_id,
                    lease_token,
                    lease_expires_at,
                    now,
                    now,
                    now,
                    row["id"],
                    JobStatus.QUEUED.value,
                ),
            )
            if updated.rowcount != 1:
                connection.commit()
                return None
            claimed = connection.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
            connection.commit()
        return Job.from_row(dict(claimed)) if claimed else None

    def refresh_lease(
        self,
        *,
        job_id: str,
        lease_token: str,
        now: str,
        lease_expires_at: str,
    ) -> Job | None:
        with self.storage.connect() as connection:
            updated = connection.execute(
                """
                UPDATE jobs
                SET
                    last_heartbeat_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = ?
                  AND lease_token = ?
                """,
                (
                    now,
                    lease_expires_at,
                    now,
                    job_id,
                    JobStatus.RUNNING.value,
                    lease_token,
                ),
            )
            if updated.rowcount != 1:
                connection.commit()
                return None
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            connection.commit()
        return Job.from_row(dict(row)) if row else None

    def _create_with_connection(self, connection: sqlite3.Connection, job: Job) -> Job:
        job.public_id = allocate_public_id(connection, table_name="jobs", prefix="J")
        connection.execute(
            """
            INSERT INTO jobs (
                id, public_id, operation_id, job_type, target_ref, status, arguments,
                dependency_job_ids, timeout_seconds, retry_limit, retry_count, queued_at,
                started_at, finished_at, last_error, lease_owner, lease_token,
                lease_expires_at, last_heartbeat_at, cancel_requested_at, cancel_reason,
                retry_after, created_at, updated_at
            ) VALUES (
                :id, :public_id, :operation_id, :job_type, :target_ref, :status, :arguments,
                :dependency_job_ids, :timeout_seconds, :retry_limit, :retry_count, :queued_at,
                :started_at, :finished_at, :last_error, :lease_owner, :lease_token,
                :lease_expires_at, :last_heartbeat_at, :cancel_requested_at, :cancel_reason,
                :retry_after, :created_at, :updated_at
            )
            """,
            job.to_row(),
        )
        return job

    def _update_with_connection(self, connection: sqlite3.Connection, job: Job) -> Job:
        connection.execute(
            """
            UPDATE jobs
            SET
                public_id = :public_id,
                operation_id = :operation_id,
                job_type = :job_type,
                target_ref = :target_ref,
                status = :status,
                arguments = :arguments,
                dependency_job_ids = :dependency_job_ids,
                timeout_seconds = :timeout_seconds,
                retry_limit = :retry_limit,
                retry_count = :retry_count,
                queued_at = :queued_at,
                started_at = :started_at,
                finished_at = :finished_at,
                last_error = :last_error,
                lease_owner = :lease_owner,
                lease_token = :lease_token,
                lease_expires_at = :lease_expires_at,
                last_heartbeat_at = :last_heartbeat_at,
                cancel_requested_at = :cancel_requested_at,
                cancel_reason = :cancel_reason,
                retry_after = :retry_after,
                created_at = :created_at,
                updated_at = :updated_at
            WHERE id = :id
            """,
            job.to_row(),
        )
        return job

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(JOBS_SCHEMA)
            self._ensure_runtime_columns(connection)
            connection.commit()

    def _ensure_runtime_columns(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(jobs)").fetchall()
        existing_columns = {row["name"] for row in rows}
        for column_name, column_type in JOB_RUNTIME_COLUMNS.items():
            if column_name in existing_columns:
                continue
            connection.execute(f"ALTER TABLE jobs ADD COLUMN {column_name} {column_type}")
