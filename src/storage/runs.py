from __future__ import annotations

from models.run import Checkpoint, Run, TaskLogEntry
from .sqlite import SQLiteStorage


RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    step_count INTEGER NOT NULL DEFAULT 0,
    last_usage TEXT NOT NULL DEFAULT '{}',
    last_error TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_task_started_at ON runs(task_id, started_at DESC);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    run_id TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task_created_at ON checkpoints(task_id, created_at DESC);

CREATE TABLE IF NOT EXISTS task_logs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    run_id TEXT,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_task_logs_task_created_at ON task_logs(task_id, created_at DESC);
"""


class RunRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create_run(self, run: Run) -> Run:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, task_id, status, started_at, finished_at, step_count, last_usage, last_error
                ) VALUES (
                    :id, :task_id, :status, :started_at, :finished_at, :step_count, :last_usage, :last_error
                )
                """,
                run.to_row(),
            )
            connection.commit()
        return run

    def get_run(self, run_id: str) -> Run | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return Run.from_row(dict(row)) if row else None

    def update_run(self, run: Run) -> Run:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET
                    task_id = :task_id,
                    status = :status,
                    started_at = :started_at,
                    finished_at = :finished_at,
                    step_count = :step_count,
                    last_usage = :last_usage,
                    last_error = :last_error
                WHERE id = :id
                """,
                run.to_row(),
            )
            connection.commit()
        return run

    def create_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (
                    id, task_id, run_id, payload, created_at
                ) VALUES (
                    :id, :task_id, :run_id, :payload, :created_at
                )
                """,
                checkpoint.to_row(),
            )
            connection.commit()
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()
        return Checkpoint.from_row(dict(row)) if row else None

    def create_log_entry(self, entry: TaskLogEntry) -> TaskLogEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO task_logs (
                    id, task_id, run_id, level, message, payload, created_at
                ) VALUES (
                    :id, :task_id, :run_id, :level, :message, :payload, :created_at
                )
                """,
                entry.to_row(),
            )
            connection.commit()
        return entry

    def list_logs(self, task_id: str, *, limit: int = 20) -> list[TaskLogEntry]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM task_logs
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [TaskLogEntry.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(RUNS_SCHEMA)
            connection.commit()
