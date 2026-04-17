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
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage
from storage.tasks import TaskRepository

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class CheckpointService:
    def __init__(
        self,
        repository: CheckpointRepository,
        session_service: SessionService,
        operation_repository: OperationRepository,
        task_repository: TaskRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.task_repository = task_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CheckpointService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            CheckpointRepository(storage),
            SessionService.from_settings(settings),
            OperationRepository(storage),
            TaskRepository(storage),
            settings,
        )

    def save_checkpoint(
        self,
        *,
        session_identifier: str | None = None,
        task_id: str | None = None,
        session_state: SessionState,
        run_id: str | None = None,
    ) -> CheckpointRecord:
        identifier = session_identifier or task_id
        if identifier is None:
            raise ValueError("session_identifier is required.")
        session = self.session_service.require_session(self._resolve_session_id(identifier))
        payload = session_state.to_checkpoint_payload()
        blob_payload = {
            "version": CHECKPOINT_SCHEMA_VERSION,
            "session_state": payload,
        }
        raw_bytes = json.dumps(blob_payload, ensure_ascii=False).encode("utf-8")
        compressed_bytes = gzip.compress(raw_bytes)
        digest = hashlib.sha256(compressed_bytes).hexdigest()
        checkpoint = StoredCheckpoint.create(
            session_id=session.id,
            run_id=run_id,
            payload_size_bytes=len(compressed_bytes),
            payload_digest=digest,
            history_message_count=len(payload.get("history", [])),
            history_text_bytes=history_text_bytes(payload),
            has_compressed_summary=bool(payload.get("compressed_summary")),
        )
        blob_path = self._resolve_blob_path(session.public_id, checkpoint.blob_path)
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

    def list_checkpoints(self, session_identifier: str, *, limit: int = 20) -> list[CheckpointSummary]:
        return self.repository.list_summaries(self._resolve_session_id(session_identifier), limit=limit)

    def delete_checkpoint(self, checkpoint_id: str) -> None:
        checkpoint = self.repository.get(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        session = self.session_service.require_session(checkpoint.session_id)
        blob_path = self._resolve_blob_path(session.public_id, checkpoint.blob_path)
        deleted = self.repository.delete(checkpoint_id)
        if not deleted:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        if blob_path.exists():
            blob_path.unlink()
            self._cleanup_empty_blob_parents(blob_path.parent, session.public_id)

    def prune_checkpoints(self, session_identifier: str, *, keep_last: int) -> int:
        if keep_last < 0:
            raise ValueError("keep_last must be greater than or equal to 0")

        checkpoints = self.repository.list_records(self._resolve_session_id(session_identifier))
        to_delete = checkpoints[keep_last:]
        for checkpoint in to_delete:
            self.delete_checkpoint(checkpoint.id)
        return len(to_delete)

    def load_checkpoint_state(self, checkpoint_id: str) -> SessionState:
        checkpoint = self.repository.get(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        if checkpoint.storage_kind != FILE_BLOB_STORAGE_KIND:
            raise ValueError(f"Unsupported checkpoint storage kind: {checkpoint.storage_kind}")
        if checkpoint.blob_encoding != FILE_BLOB_ENCODING:
            raise ValueError(f"Unsupported checkpoint encoding: {checkpoint.blob_encoding}")

        session = self.session_service.require_session(checkpoint.session_id)
        blob_path = self._resolve_blob_path(session.public_id, checkpoint.blob_path)
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

    def _resolve_blob_path(self, session_public_id: str, relative_blob_path: str | None) -> Path:
        if not relative_blob_path:
            raise ValueError("Checkpoint blob path is missing.")
        app_root = self.settings.app_data_dir.resolve()
        resolved = (app_root / relative_blob_path).resolve()
        if os.path.commonpath([str(resolved), str(app_root)]) != str(app_root):
            raise ValueError(f"Checkpoint blob path escapes app data directory: {relative_blob_path}")
        return resolved

    def _write_blob(self, blob_path: Path, payload: bytes) -> None:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = blob_path.with_name(blob_path.name + ".tmp")
        temp_path.write_bytes(payload)
        os.replace(temp_path, blob_path)

    def _cleanup_empty_blob_parents(self, path: Path, session_public_id: str) -> None:
        checkpoints_root = (self.settings.app_data_dir / "memory" / "checkpoints").resolve()
        current = path.resolve()
        while current != checkpoints_root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _resolve_session_id(self, identifier: str) -> str:
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
            task_repository=self.task_repository,
        )
