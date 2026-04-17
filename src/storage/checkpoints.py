from __future__ import annotations

from models.checkpoint import CheckpointRecord, CheckpointSummary, StoredCheckpoint
from storage.repositories.sessions import SessionRepository
from storage.schema_guard import ensure_phase6_clean_runtime_reset

from .runs import RunRepository
from .sqlite import SQLiteStorage


METADATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    storage_kind TEXT NOT NULL,
    blob_path TEXT NOT NULL,
    blob_encoding TEXT NOT NULL,
    payload_size_bytes INTEGER NOT NULL,
    payload_digest TEXT NOT NULL,
    history_message_count INTEGER NOT NULL,
    history_text_bytes INTEGER NOT NULL,
    has_compressed_summary INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES sessions(id),
    FOREIGN KEY(run_id) REFERENCES session_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_session_checkpoints_session_created_at
    ON session_checkpoints(session_id, created_at DESC);
"""


class CheckpointRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, checkpoint: StoredCheckpoint) -> StoredCheckpoint:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_checkpoints (
                    id, session_id, run_id, created_at, storage_kind, blob_path, blob_encoding,
                    payload_size_bytes, payload_digest, history_message_count, history_text_bytes,
                    has_compressed_summary
                ) VALUES (
                    :id, :session_id, :run_id, :created_at, :storage_kind, :blob_path, :blob_encoding,
                    :payload_size_bytes, :payload_digest, :history_message_count, :history_text_bytes,
                    :has_compressed_summary
                )
                """,
                checkpoint.to_row(),
            )
            connection.commit()
        return checkpoint

    def get(self, checkpoint_id: str) -> StoredCheckpoint | None:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT * FROM session_checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()
        return StoredCheckpoint.from_row(dict(row)) if row else None

    def get_record(self, checkpoint_id: str) -> CheckpointRecord | None:
        checkpoint = self.get(checkpoint_id)
        return checkpoint.to_record() if checkpoint is not None else None

    def get_summary(self, checkpoint_id: str) -> CheckpointSummary | None:
        checkpoint = self.get(checkpoint_id)
        return checkpoint.to_summary() if checkpoint is not None else None

    def list_summaries(self, session_id: str, *, limit: int = 20) -> list[CheckpointSummary]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM session_checkpoints
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [StoredCheckpoint.from_row(dict(row)).to_summary() for row in rows]

    def list_records(self, session_id: str, *, limit: int | None = None) -> list[CheckpointRecord]:
        sql = """
            SELECT *
            FROM session_checkpoints
            WHERE session_id = ?
            ORDER BY created_at DESC
        """
        parameters: tuple[object, ...]
        if limit is None:
            parameters = (session_id,)
        else:
            sql += "\nLIMIT ?"
            parameters = (session_id, limit)
        with self.storage.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [StoredCheckpoint.from_row(dict(row)).to_record() for row in rows]

    def delete(self, checkpoint_id: str) -> bool:
        with self.storage.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM session_checkpoints WHERE id = ?",
                (checkpoint_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        RunRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(METADATA_SCHEMA)
            connection.commit()
