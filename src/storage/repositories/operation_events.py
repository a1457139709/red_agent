from __future__ import annotations

from models.operation_event import OperationEvent, OperationEventType
from storage.sqlite import SQLiteStorage


OPERATION_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS operation_events (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
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
    FOREIGN KEY(operation_id) REFERENCES operations(id),
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_operation_events_operation_created_at
    ON operation_events(operation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_operation_events_operation_type_created_at
    ON operation_events(operation_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_operation_events_job_created_at
    ON operation_events(job_id, created_at DESC);
"""


class OperationEventRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, event: OperationEvent) -> OperationEvent:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO operation_events (
                    id, operation_id, job_id, event_type, level, tool_name, tool_category,
                    target_ref, reason_code, message, payload, created_at
                ) VALUES (
                    :id, :operation_id, :job_id, :event_type, :level, :tool_name, :tool_category,
                    :target_ref, :reason_code, :message, :payload, :created_at
                )
                """,
                event.to_row(),
            )
            connection.commit()
        return event

    def list(self, operation_id: str, *, limit: int | None = 50) -> list[OperationEvent]:
        query = """
            SELECT *
            FROM operation_events
            WHERE operation_id = ?
            ORDER BY created_at DESC
        """
        params: list[object] = [operation_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [OperationEvent.from_row(dict(row)) for row in rows]

    def count_since(
        self,
        operation_id: str,
        *,
        event_type: OperationEventType | None = None,
        since: str | None = None,
    ) -> int:
        query = "SELECT COUNT(*) AS count FROM operation_events WHERE operation_id = ?"
        params: list[object] = [operation_id]
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
        with self.storage.connect() as connection:
            connection.executescript(OPERATION_EVENTS_SCHEMA)
            connection.commit()
