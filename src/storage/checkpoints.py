from __future__ import annotations

from models.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointRecord,
    CheckpointSummary,
    StoredCheckpoint,
)

from .sqlite import SQLiteStorage


METADATA_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
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
    FOREIGN KEY(task_id) REFERENCES tasks(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task_created_at ON checkpoints(task_id, created_at DESC);
"""


class CheckpointRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        self._ensure_schema()

    def create(self, checkpoint: StoredCheckpoint) -> StoredCheckpoint:
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (
                    id, task_id, run_id, created_at, storage_kind, blob_path, blob_encoding,
                    payload_size_bytes, payload_digest, history_message_count, history_text_bytes,
                    has_compressed_summary
                ) VALUES (
                    :id, :task_id, :run_id, :created_at, :storage_kind, :blob_path, :blob_encoding,
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
                "SELECT * FROM checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()
        return StoredCheckpoint.from_row(dict(row)) if row else None

    def get_record(self, checkpoint_id: str) -> CheckpointRecord | None:
        checkpoint = self.get(checkpoint_id)
        return checkpoint.to_record() if checkpoint is not None else None

    def get_summary(self, checkpoint_id: str) -> CheckpointSummary | None:
        checkpoint = self.get(checkpoint_id)
        return checkpoint.to_summary() if checkpoint is not None else None

    def list_summaries(self, task_id: str, *, limit: int = 20) -> list[CheckpointSummary]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM checkpoints
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [StoredCheckpoint.from_row(dict(row)).to_summary() for row in rows]

    def list_records(self, task_id: str, *, limit: int | None = None) -> list[CheckpointRecord]:
        sql = """
            SELECT *
            FROM checkpoints
            WHERE task_id = ?
            ORDER BY created_at DESC
        """
        parameters: tuple[object, ...]
        if limit is None:
            parameters = (task_id,)
        else:
            sql += "\nLIMIT ?"
            parameters = (task_id, limit)
        with self.storage.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [StoredCheckpoint.from_row(dict(row)).to_record() for row in rows]

    def delete(self, checkpoint_id: str) -> bool:
        with self.storage.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM checkpoints WHERE id = ?",
                (checkpoint_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def _ensure_schema(self) -> None:
        with self.storage.connect() as connection:
            self._fail_if_legacy_checkpoint_schema(connection)
            connection.executescript(METADATA_SCHEMA)
            connection.execute(
                """
                INSERT OR IGNORE INTO app_metadata(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(CHECKPOINT_SCHEMA_VERSION),),
            )
            self._validate_schema_version(connection)
            connection.commit()

    def _fail_if_legacy_checkpoint_schema(self, connection) -> None:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'checkpoints'"
        ).fetchone()
        if row is None:
            return
        columns = {
            item["name"]
            for item in connection.execute("PRAGMA table_info(checkpoints)").fetchall()
        }
        if "payload" in columns:
            raise ValueError(
                "This workspace uses an older checkpoint schema. Delete or migrate "
                "`.red-code/agent.db` before running the new runtime."
            )

    def _validate_schema_version(self, connection) -> None:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise ValueError("Missing schema_version metadata.")
        if str(row["value"]) != str(CHECKPOINT_SCHEMA_VERSION):
            raise ValueError(
                f"Unsupported checkpoint schema version: {row['value']}. "
                f"Expected {CHECKPOINT_SCHEMA_VERSION}."
            )
