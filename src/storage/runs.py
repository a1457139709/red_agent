from __future__ import annotations

from models.run import Run, SessionLogEntry
from storage.repositories.sessions import SessionRepository
from storage.schema_guard import ensure_phase6_clean_runtime_reset

from .sqlite import SQLiteStorage


RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_runs (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    session_id TEXT NOT NULL,
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
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_runs_public_id ON session_runs(public_id);
CREATE INDEX IF NOT EXISTS idx_session_runs_session_started_at
    ON session_runs(session_id, started_at DESC);

CREATE TABLE IF NOT EXISTS session_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    run_id TEXT,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(run_id) REFERENCES session_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_session_logs_session_created_at
    ON session_logs(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_logs_run_created_at
    ON session_logs(run_id, created_at DESC);
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
                INSERT INTO session_runs (
                    id, public_id, session_id, status, started_at, finished_at, step_count, last_usage,
                    last_error, duration_ms, effective_skill_name, effective_tools, failure_kind
                ) VALUES (
                    :id, :public_id, :session_id, :status, :started_at, :finished_at, :step_count, :last_usage,
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

    def list_runs(self, session_id: str, *, limit: int = 20) -> list[Run]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM session_runs
                WHERE session_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [Run.from_row(dict(row)) for row in rows]

    def update_run(self, run: Run) -> Run:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE session_runs
                SET
                    public_id = :public_id,
                    session_id = :session_id,
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

    def create_log_entry(self, entry: SessionLogEntry) -> SessionLogEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_logs (
                    id, session_id, run_id, level, message, payload, created_at
                ) VALUES (
                    :id, :session_id, :run_id, :level, :message, :payload, :created_at
                )
                """,
                entry.to_row(),
            )
            connection.commit()
        return entry

    def list_logs(self, session_id: str, *, limit: int = 20) -> list[SessionLogEntry]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM session_logs
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [SessionLogEntry.from_row(dict(row)) for row in rows]

    def list_logs_for_run(self, run_id: str, *, limit: int = 20) -> list[SessionLogEntry]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM session_logs
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [SessionLogEntry.from_row(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(RUNS_SCHEMA)
            connection.commit()

    def _get_run_row_by_identifier(self, connection, identifier: str):
        row = connection.execute(
            "SELECT * FROM session_runs WHERE public_id = ?",
            (identifier,),
        ).fetchone()
        if row is not None:
            return row
        row = connection.execute(
            "SELECT * FROM session_runs WHERE id = ?",
            (identifier,),
        ).fetchone()
        if row is not None:
            return row
        prefix_rows = connection.execute(
            "SELECT * FROM session_runs WHERE id LIKE ? ORDER BY started_at DESC LIMIT 2",
            (f"{identifier}%",),
        ).fetchall()
        if len(prefix_rows) == 1:
            return prefix_rows[0]
        return None

    def _allocate_public_id(self, connection) -> str:
        row = connection.execute(
            """
            SELECT public_id
            FROM session_runs
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
