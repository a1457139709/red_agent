from __future__ import annotations

from models.memory import MemoryEntry
from storage.schema_guard import ensure_phase6_clean_runtime_reset
from storage.sqlite import SQLiteStorage

from .sessions import SessionRepository


MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_memory_entries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_job_id TEXT,
    entry_type TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(source_job_id) REFERENCES session_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_session_memory_entries_session_updated_at
    ON session_memory_entries(session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_memory_entries_key ON session_memory_entries(key);
"""


class MemoryRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, entry: MemoryEntry) -> MemoryEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_memory_entries (
                    id, session_id, source_job_id, entry_type, key, value, summary, created_at, updated_at
                ) VALUES (
                    :id, :session_id, :source_job_id, :entry_type, :key, :value, :summary, :created_at, :updated_at
                )
                """,
                entry.to_row(),
            )
            connection.commit()
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM session_memory_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return MemoryEntry.from_row(dict(row)) if row else None

    def list(self, session_id: str, *, limit: int | None = 50) -> list[MemoryEntry]:
        query = "SELECT * FROM session_memory_entries WHERE session_id = ? ORDER BY updated_at DESC"
        params: list[object] = [session_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [MemoryEntry.from_row(dict(row)) for row in rows]

    def count(self, session_id: str) -> int:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM session_memory_entries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def update(self, entry: MemoryEntry) -> MemoryEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE session_memory_entries
                SET
                    session_id = :session_id,
                    source_job_id = :source_job_id,
                    entry_type = :entry_type,
                    key = :key,
                    value = :value,
                    summary = :summary,
                    created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                entry.to_row(),
            )
            connection.commit()
        return entry

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(MEMORY_SCHEMA)
            connection.commit()
