from __future__ import annotations

from models.job import Job, JobLogEntry, JobStatus
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_public_id ON jobs(public_id);
CREATE INDEX IF NOT EXISTS idx_jobs_operation_updated_at ON jobs(operation_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

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

    def count_running(self, operation_id: str) -> int:
        with self.storage.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE operation_id = ? AND status = ?
                """,
                (operation_id, JobStatus.RUNNING.value),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def _create_with_connection(self, connection, job: Job) -> Job:
        job.public_id = allocate_public_id(connection, table_name="jobs", prefix="J")
        connection.execute(
            """
            INSERT INTO jobs (
                id, public_id, operation_id, job_type, target_ref, status, arguments,
                dependency_job_ids, timeout_seconds, retry_limit, retry_count, queued_at,
                started_at, finished_at, last_error, created_at, updated_at
            ) VALUES (
                :id, :public_id, :operation_id, :job_type, :target_ref, :status, :arguments,
                :dependency_job_ids, :timeout_seconds, :retry_limit, :retry_count, :queued_at,
                :started_at, :finished_at, :last_error, :created_at, :updated_at
            )
            """,
            job.to_row(),
        )
        return job

    def _update_with_connection(self, connection, job: Job) -> Job:
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
            connection.commit()
