from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path

from agent.settings import Settings, get_settings
from agent.state import SessionState
from models.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    FILE_BLOB_ENCODING,
    FILE_BLOB_STORAGE_KIND,
    CheckpointRecord,
    CheckpointSummary,
    StoredCheckpoint,
    history_text_bytes,
)
from storage.checkpoints import CheckpointRepository
from storage.sqlite import SQLiteStorage


class CheckpointService:
    def __init__(self, repository: CheckpointRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CheckpointService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        repository = CheckpointRepository(storage)
        return cls(repository, settings)

    def save_checkpoint(
        self,
        *,
        task_id: str,
        session_state: SessionState,
        run_id: str | None = None,
    ) -> CheckpointRecord:
        payload = session_state.to_checkpoint_payload()
        blob_payload = {
            "version": CHECKPOINT_SCHEMA_VERSION,
            "session_state": payload,
        }
        raw_bytes = json.dumps(blob_payload, ensure_ascii=False).encode("utf-8")
        compressed_bytes = gzip.compress(raw_bytes)
        digest = hashlib.sha256(compressed_bytes).hexdigest()
        checkpoint = StoredCheckpoint.create(
            task_id=task_id,
            run_id=run_id,
            payload_size_bytes=len(compressed_bytes),
            payload_digest=digest,
            history_message_count=len(payload.get("history", [])),
            history_text_bytes=history_text_bytes(payload),
            has_compressed_summary=bool(payload.get("compressed_summary")),
        )
        blob_path = self._resolve_blob_path(checkpoint.blob_path)
        self._write_blob(blob_path, compressed_bytes)
        created = self.repository.create(checkpoint)
        return created.to_record()

    def get_checkpoint_record(self, checkpoint_id: str) -> CheckpointRecord | None:
        return self.repository.get_record(checkpoint_id)

    def require_checkpoint_record(self, checkpoint_id: str) -> CheckpointRecord:
        checkpoint = self.get_checkpoint_record(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        return checkpoint

    def get_checkpoint_summary(self, checkpoint_id: str) -> CheckpointSummary | None:
        return self.repository.get_summary(checkpoint_id)

    def require_checkpoint_summary(self, checkpoint_id: str) -> CheckpointSummary:
        checkpoint = self.get_checkpoint_summary(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        return checkpoint

    def list_checkpoints(self, task_id: str, *, limit: int = 20) -> list[CheckpointSummary]:
        return self.repository.list_summaries(task_id, limit=limit)

    def load_checkpoint_state(self, checkpoint_id: str) -> SessionState:
        checkpoint = self.repository.get(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        if checkpoint.storage_kind != FILE_BLOB_STORAGE_KIND:
            raise ValueError(f"Unsupported checkpoint storage kind: {checkpoint.storage_kind}")
        if checkpoint.blob_encoding != FILE_BLOB_ENCODING:
            raise ValueError(f"Unsupported checkpoint encoding: {checkpoint.blob_encoding}")

        blob_path = self._resolve_blob_path(checkpoint.blob_path)
        if not blob_path.exists():
            raise ValueError(f"Checkpoint blob not found: {checkpoint.blob_path}")

        blob_bytes = blob_path.read_bytes()
        digest = hashlib.sha256(blob_bytes).hexdigest()
        if digest != checkpoint.payload_digest:
            raise ValueError(f"Checkpoint blob digest mismatch: {checkpoint.id}")

        try:
            payload = json.loads(gzip.decompress(blob_bytes).decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to read checkpoint blob: {checkpoint.id}") from exc

        version = payload.get("version")
        if version != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported checkpoint payload version: {version}")

        session_payload = payload.get("session_state")
        if not isinstance(session_payload, dict):
            raise ValueError(f"Invalid checkpoint payload: {checkpoint.id}")
        return SessionState.from_checkpoint_payload(session_payload)

    def _resolve_blob_path(self, relative_blob_path: str | None) -> Path:
        if not relative_blob_path:
            raise ValueError("Checkpoint blob path is missing.")
        path = (self.settings.app_data_dir / relative_blob_path).resolve()
        checkpoints_root = self.settings.checkpoints_dir.resolve()
        if os.path.commonpath([str(path), str(checkpoints_root)]) != str(checkpoints_root):
            raise ValueError(f"Checkpoint blob path escapes checkpoints directory: {relative_blob_path}")
        return path

    def _write_blob(self, blob_path: Path, payload: bytes) -> None:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = blob_path.with_name(blob_path.name + ".tmp")
        temp_path.write_bytes(payload)
        os.replace(temp_path, blob_path)
