from __future__ import annotations

from models.memory import MemoryEntry
from storage.sqlite import SQLiteStorage


MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    source_job_id TEXT,
    entry_type TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(id),
    FOREIGN KEY(source_job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_memory_entries_operation_updated_at ON memory_entries(operation_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_entries_key ON memory_entries(key);
"""


class MemoryRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, entry: MemoryEntry) -> MemoryEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_entries (
                    id, operation_id, source_job_id, entry_type, key, value, summary, created_at, updated_at
                ) VALUES (
                    :id, :operation_id, :source_job_id, :entry_type, :key, :value, :summary, :created_at, :updated_at
                )
                """,
                entry.to_row(),
            )
            connection.commit()
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return MemoryEntry.from_row(dict(row)) if row else None

    def list(self, operation_id: str, *, limit: int | None = 50) -> list[MemoryEntry]:
        query = "SELECT * FROM memory_entries WHERE operation_id = ? ORDER BY updated_at DESC"
        params: list[object] = [operation_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [MemoryEntry.from_row(dict(row)) for row in rows]

    def update(self, entry: MemoryEntry) -> MemoryEntry:
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE memory_entries
                SET
                    operation_id = :operation_id,
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
        with self.storage.connect() as connection:
            connection.executescript(MEMORY_SCHEMA)
            connection.commit()
