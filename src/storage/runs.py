from __future__ import annotations

from models.run import Run, TaskLogEntry
from .sqlite import SQLiteStorage


RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    step_count INTEGER NOT NULL DEFAULT 0,
    last_usage TEXT NOT NULL DEFAULT '{}',
    last_error TEXT,
    duration_ms INTEGER,
    effective_skill_name TEXT,
    effective_tools TEXT NOT NULL DEFAULT '[]',
    failure_kind TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_public_id ON runs(public_id);
CREATE INDEX IF NOT EXISTS idx_runs_task_started_at ON runs(task_id, started_at DESC);

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
CREATE INDEX IF NOT EXISTS idx_task_logs_run_created_at ON task_logs(run_id, created_at DESC);
"""


class RunRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create_run(self, run: Run) -> Run:
        with self.storage.connect() as connection:
            run.public_id = self._allocate_public_id(connection)
            connection.execute(
                """
                INSERT INTO runs (
                    id, public_id, task_id, status, started_at, finished_at, step_count, last_usage,
                    last_error, duration_ms, effective_skill_name, effective_tools, failure_kind
                ) VALUES (
                    :id, :public_id, :task_id, :status, :started_at, :finished_at, :step_count, :last_usage,
                    :last_error, :duration_ms, :effective_skill_name, :effective_tools, :failure_kind
                )
                """,
                run.to_row(),
            )
            connection.commit()
        return run

    def get_run(self, run_id: str) -> Run | None:
        with self.storage.connect() as connection:
            row = self._get_run_row_by_identifier(connection, run_id)
        return Run.from_row(dict(row)) if row else None

    def list_runs(self, task_id: str, *, limit: int = 20) -> list[Run]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM runs
                WHERE task_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [Run.from_row(dict(row)) for row in rows]

    def update_run(self, run: Run) -> Run:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET
                    public_id = :public_id,
                    task_id = :task_id,
                    status = :status,
                    started_at = :started_at,
                    finished_at = :finished_at,
                    step_count = :step_count,
                    last_usage = :last_usage,
                    last_error = :last_error,
                    duration_ms = :duration_ms,
                    effective_skill_name = :effective_skill_name,
                    effective_tools = :effective_tools,
                    failure_kind = :failure_kind
                WHERE id = :id
                """,
                run.to_row(),
            )
            connection.commit()
        return run

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

    def list_logs_for_run(self, run_id: str, *, limit: int = 20) -> list[TaskLogEntry]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM task_logs
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [TaskLogEntry.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            connection.executescript(RUNS_SCHEMA)
            self._ensure_run_columns(connection)
            self._backfill_run_public_ids(connection)
            connection.commit()

    def _ensure_run_columns(self, connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        missing_sql = {
            "public_id": "ALTER TABLE runs ADD COLUMN public_id TEXT",
            "duration_ms": "ALTER TABLE runs ADD COLUMN duration_ms INTEGER",
            "effective_skill_name": "ALTER TABLE runs ADD COLUMN effective_skill_name TEXT",
            "effective_tools": "ALTER TABLE runs ADD COLUMN effective_tools TEXT NOT NULL DEFAULT '[]'",
            "failure_kind": "ALTER TABLE runs ADD COLUMN failure_kind TEXT",
        }
        for column_name, sql in missing_sql.items():
            if column_name not in columns:
                connection.execute(sql)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_public_id ON runs(public_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_logs_run_created_at ON task_logs(run_id, created_at DESC)"
        )

    def _backfill_run_public_ids(self, connection) -> None:
        rows = connection.execute(
            "SELECT id FROM runs WHERE public_id IS NULL OR public_id = '' ORDER BY started_at ASC, id ASC"
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE runs SET public_id = ? WHERE id = ?",
                (self._allocate_public_id(connection), row["id"]),
            )

    def _get_run_row_by_identifier(self, connection, identifier: str):
        row = connection.execute(
            "SELECT * FROM runs WHERE public_id = ?",
            (identifier,),
        ).fetchone()
        if row is not None:
            return row

        row = connection.execute(
            "SELECT * FROM runs WHERE id = ?",
            (identifier,),
        ).fetchone()
        if row is not None:
            return row

        prefix_rows = connection.execute(
            "SELECT * FROM runs WHERE id LIKE ? ORDER BY started_at DESC LIMIT 2",
            (f"{identifier}%",),
        ).fetchall()
        if len(prefix_rows) == 1:
            return prefix_rows[0]
        return None

    def _allocate_public_id(self, connection) -> str:
        row = connection.execute(
            """
            SELECT public_id
            FROM runs
            WHERE public_id LIKE 'R%'
            ORDER BY CAST(SUBSTR(public_id, 2) AS INTEGER) DESC
            LIMIT 1
            """
        ).fetchone()
        next_number = 1
        if row is not None and row["public_id"]:
            try:
                next_number = int(str(row["public_id"])[1:]) + 1
            except ValueError:
                next_number = 1
        return f"R{next_number:04d}"
