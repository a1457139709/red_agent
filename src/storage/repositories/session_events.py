from __future__ import annotations

from models.session_event import SessionEvent, SessionEventType
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from .sessions import SessionRepository


SESSION_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    job_id TEXT,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_category TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    reason_code TEXT,
    message TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(job_id) REFERENCES session_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_session_events_session_created_at
    ON session_events(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_events_session_type_created_at
    ON session_events(session_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_events_job_created_at
    ON session_events(job_id, created_at DESC);
"""


class SessionEventRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, event: SessionEvent) -> SessionEvent:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_events (
                    id, session_id, job_id, event_type, level, tool_name, tool_category,
                    target_ref, reason_code, message, payload, created_at
                ) VALUES (
                    :id, :session_id, :job_id, :event_type, :level, :tool_name, :tool_category,
                    :target_ref, :reason_code, :message, :payload, :created_at
                )
                """,
                event.to_row(),
            )
            connection.commit()
        return event

    def list(self, session_id: str, *, limit: int | None = 50) -> list[SessionEvent]:
        query = """
            SELECT *
            FROM session_events
            WHERE session_id = ?
            ORDER BY created_at DESC
        """
        params: list[object] = [session_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [SessionEvent.from_row(dict(row)) for row in rows]

    def count_since(
        self,
        session_id: str,
        *,
        event_type: SessionEventType | None = None,
        since: str | None = None,
    ) -> int:
        query = "SELECT COUNT(*) AS count FROM session_events WHERE session_id = ?"
        params: list[object] = [session_id]
        if event_type is not None:
            query += " AND event_type = ?"
            params.append(event_type.value)
        if since is not None:
            query += " AND created_at >= ?"
            params.append(since)
        with self.storage.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["count"]) if row is not None else 0

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(SESSION_EVENTS_SCHEMA)
            connection.commit()
