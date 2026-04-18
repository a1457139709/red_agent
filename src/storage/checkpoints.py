from __future__ import annotations

import hashlib
import os
from pathlib import Path

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
        query = """
            SELECT *
            FROM session_checkpoints
            WHERE session_id = ?
            ORDER BY created_at DESC
        """
        params: list[object] = [session_id]
        if limit is not None:
            query += "\nLIMIT ?"
            params.append(limit)
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
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

    def count(self, session_id: str) -> int:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM session_checkpoints WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def _ensure_schema(self) -> None:
        SessionRepository(self.storage)
        RunRepository(self.storage)
        with self.storage.connect() as connection:
            ensure_phase6_clean_runtime_reset(connection, app_data_dir=self.storage.db_path.parent)
            connection.executescript(METADATA_SCHEMA)
            self._migrate_legacy_blob_paths(connection)
            connection.commit()

    def _migrate_legacy_blob_paths(self, connection) -> None:
        rows = connection.execute(
            """
            SELECT
                session_checkpoints.id,
                session_checkpoints.blob_path,
                session_checkpoints.payload_digest,
                session_checkpoints.session_id,
                sessions.public_id AS session_public_id
            FROM session_checkpoints
            INNER JOIN sessions ON sessions.id = session_checkpoints.session_id
            """
        ).fetchall()
        app_root = self.storage.db_path.parent.resolve()
        for row in rows:
            legacy_relative_path = str(row["blob_path"]).replace("\\", "/")
            target_relative_path = self._target_relative_path(
                session_id=row["session_id"],
                session_public_id=row["session_public_id"],
                current_relative_path=legacy_relative_path,
            )
            if target_relative_path == legacy_relative_path:
                continue
            legacy_path = self._resolve_app_relative_path(app_root, legacy_relative_path)
            target_path = self._resolve_app_relative_path(app_root, target_relative_path)
            self._migrate_single_blob_path(
                checkpoint_id=row["id"],
                payload_digest=row["payload_digest"],
                legacy_path=legacy_path,
                target_path=target_path,
            )
            connection.execute(
                "UPDATE session_checkpoints SET blob_path = ? WHERE id = ?",
                (target_relative_path, row["id"]),
            )

    def _target_relative_path(
        self,
        *,
        session_id: str,
        session_public_id: str,
        current_relative_path: str,
    ) -> str:
        normalized_relative_path = current_relative_path.replace("\\", "/")
        if normalized_relative_path.startswith(f"sessions/{session_id}/memory/checkpoints/"):
            return normalized_relative_path

        if normalized_relative_path.startswith(f"sessions/{session_public_id}/memory/checkpoints/"):
            suffix = normalized_relative_path.removeprefix(f"sessions/{session_public_id}/")
            return f"sessions/{session_id}/{suffix}"

        if normalized_relative_path.startswith("memory/checkpoints/"):
            return f"sessions/{session_id}/{normalized_relative_path}"

        return normalized_relative_path

    def _migrate_single_blob_path(
        self,
        *,
        checkpoint_id: str,
        payload_digest: str,
        legacy_path: Path,
        target_path: Path,
    ) -> None:
        legacy_exists = legacy_path.exists()
        target_exists = target_path.exists()

        if legacy_exists and target_exists:
            legacy_digest = self._digest_file(legacy_path)
            target_digest = self._digest_file(target_path)
            if legacy_digest != target_digest:
                raise ValueError(
                    "Checkpoint blob migration conflict detected for "
                    f"{checkpoint_id}: legacy and target files differ."
                )
            if target_digest != payload_digest:
                raise ValueError(
                    "Checkpoint blob migration digest mismatch for "
                    f"{checkpoint_id}: target file does not match metadata."
                )
            legacy_path.unlink()
            self._cleanup_empty_directories(legacy_path.parent, stop_at=legacy_path.parents[2])
            return

        if legacy_exists:
            legacy_digest = self._digest_file(legacy_path)
            if legacy_digest != payload_digest:
                raise ValueError(
                    "Checkpoint blob migration digest mismatch for "
                    f"{checkpoint_id}: legacy file does not match metadata."
                )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(legacy_path, target_path)
            self._cleanup_empty_directories(legacy_path.parent, stop_at=legacy_path.parents[2])
            return

        if target_exists:
            target_digest = self._digest_file(target_path)
            if target_digest != payload_digest:
                raise ValueError(
                    "Checkpoint blob migration digest mismatch for "
                    f"{checkpoint_id}: target file does not match metadata."
                )
            return

        raise ValueError(
            "Checkpoint blob migration failed for "
            f"{checkpoint_id}: neither legacy nor target file exists."
        )

    def _resolve_app_relative_path(self, app_root: Path, relative_path: str) -> Path:
        normalized_relative_path = relative_path.replace("\\", "/")
        resolved = (app_root / normalized_relative_path).resolve()
        if os.path.commonpath([str(resolved), str(app_root)]) != str(app_root):
            raise ValueError(f"Checkpoint blob path escapes app data directory: {relative_path}")
        return resolved

    def _digest_file(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _cleanup_empty_directories(self, path: Path, *, stop_at: Path) -> None:
        current = path.resolve()
        stop_path = stop_at.resolve()
        while current != stop_path:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
