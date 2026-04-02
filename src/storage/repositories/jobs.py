from __future__ import annotations

from domain.jobs import Job, JobStatus
from storage.redteam import RedTeamStorage


class JobRepository:
    def __init__(self, storage: RedTeamStorage) -> None:
        self.storage = storage

    def create(self, job: Job) -> Job:
        with self.storage.connect() as connection:
            job.public_id = self._allocate_public_id(connection)
            connection.execute(
                """
                INSERT INTO jobs (
                    id, public_id, operation_id, planner_run_id, parent_job_id, job_type,
                    tool_name, target_ref, status, priority, args_json, result_summary,
                    timeout_seconds, max_retries, retry_count, worker_id, lease_expires_at,
                    queued_at, started_at, heartbeat_at, finished_at, error_code,
                    error_message, created_at, updated_at
                ) VALUES (
                    :id, :public_id, :operation_id, :planner_run_id, :parent_job_id, :job_type,
                    :tool_name, :target_ref, :status, :priority, :args_json, :result_summary,
                    :timeout_seconds, :max_retries, :retry_count, :worker_id, :lease_expires_at,
                    :queued_at, :started_at, :heartbeat_at, :finished_at, :error_code,
                    :error_message, :created_at, :updated_at
                )
                """,
                job.to_row(),
            )
            connection.commit()
        return job

    def get(self, identifier: str) -> Job | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE public_id = ? OR id = ?",
                (identifier, identifier),
            ).fetchone()
        return Job.from_row(dict(row)) if row else None

    def list_by_operation(
        self,
        operation_id: str,
        *,
        status: JobStatus | None = None,
        limit: int | None = None,
    ) -> list[Job]:
        query = "SELECT * FROM jobs WHERE operation_id = ?"
        params: list[object] = [operation_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Job.from_row(dict(row)) for row in rows]

    def update(self, job: Job) -> Job:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET
                    public_id = :public_id,
                    operation_id = :operation_id,
                    planner_run_id = :planner_run_id,
                    parent_job_id = :parent_job_id,
                    job_type = :job_type,
                    tool_name = :tool_name,
                    target_ref = :target_ref,
                    status = :status,
                    priority = :priority,
                    args_json = :args_json,
                    result_summary = :result_summary,
                    timeout_seconds = :timeout_seconds,
                    max_retries = :max_retries,
                    retry_count = :retry_count,
                    worker_id = :worker_id,
                    lease_expires_at = :lease_expires_at,
                    queued_at = :queued_at,
                    started_at = :started_at,
                    heartbeat_at = :heartbeat_at,
                    finished_at = :finished_at,
                    error_code = :error_code,
                    error_message = :error_message,
                    created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                job.to_row(),
            )
            connection.commit()
        return job

    def _allocate_public_id(self, connection) -> str:
        row = connection.execute(
            """
            SELECT public_id
            FROM jobs
            WHERE public_id LIKE 'J%'
            ORDER BY CAST(SUBSTR(public_id, 2) AS INTEGER) DESC
            LIMIT 1
            """
        ).fetchone()
        next_number = 1
        if row is not None and row["public_id"]:
            next_number = int(str(row["public_id"])[1:]) + 1
        return f"J{next_number:04d}"
