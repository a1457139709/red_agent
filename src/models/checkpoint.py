from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


CHECKPOINT_SCHEMA_VERSION = 2
FILE_BLOB_STORAGE_KIND = "file_blob"
FILE_BLOB_ENCODING = "json+gzip"


def history_text_bytes(payload: dict[str, Any]) -> int:
    total = 0
    for message in payload.get("history", []):
        content = message.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            total += len(content.encode("utf-8"))
        else:
            total += len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
    return total


def build_blob_relative_path(*, checkpoint_id: str, created_at: str) -> str:
    created = datetime.fromisoformat(created_at)
    return f"checkpoints/{created.year:04d}/{created.month:02d}/chk_{checkpoint_id}.json.gz"


@dataclass(slots=True)
class CheckpointRecord:
    id: str
    task_id: str
    run_id: str | None
    created_at: str
    storage_kind: str = FILE_BLOB_STORAGE_KIND
    blob_path: str | None = None
    blob_encoding: str | None = FILE_BLOB_ENCODING
    payload_digest: str | None = None


@dataclass(slots=True)
class CheckpointSummary:
    id: str
    task_id: str
    run_id: str | None
    created_at: str
    storage_kind: str
    payload_size_bytes: int
    history_message_count: int
    history_text_bytes: int
    has_compressed_summary: bool


@dataclass(slots=True)
class StoredCheckpoint:
    id: str
    task_id: str
    run_id: str | None
    created_at: str = field(default_factory=utc_now_iso)
    storage_kind: str = FILE_BLOB_STORAGE_KIND
    blob_path: str | None = None
    blob_encoding: str | None = FILE_BLOB_ENCODING
    payload_size_bytes: int = 0
    payload_digest: str | None = None
    history_message_count: int = 0
    history_text_bytes: int = 0
    has_compressed_summary: bool = False

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        run_id: str | None = None,
        payload_size_bytes: int,
        payload_digest: str,
        history_message_count: int,
        history_text_bytes: int,
        has_compressed_summary: bool,
    ) -> "StoredCheckpoint":
        checkpoint_id = str(uuid4())
        created_at = utc_now_iso()
        return cls(
            id=checkpoint_id,
            task_id=task_id,
            run_id=run_id,
            created_at=created_at,
            blob_path=build_blob_relative_path(
                checkpoint_id=checkpoint_id,
                created_at=created_at,
            ),
            payload_size_bytes=payload_size_bytes,
            payload_digest=payload_digest,
            history_message_count=history_message_count,
            history_text_bytes=history_text_bytes,
            has_compressed_summary=has_compressed_summary,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "StoredCheckpoint":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row["run_id"],
            created_at=row["created_at"],
            storage_kind=row["storage_kind"],
            blob_path=row["blob_path"],
            blob_encoding=row["blob_encoding"],
            payload_size_bytes=row["payload_size_bytes"],
            payload_digest=row["payload_digest"],
            history_message_count=row["history_message_count"],
            history_text_bytes=row["history_text_bytes"],
            has_compressed_summary=bool(row["has_compressed_summary"]),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "storage_kind": self.storage_kind,
            "blob_path": self.blob_path,
            "blob_encoding": self.blob_encoding,
            "payload_size_bytes": self.payload_size_bytes,
            "payload_digest": self.payload_digest,
            "history_message_count": self.history_message_count,
            "history_text_bytes": self.history_text_bytes,
            "has_compressed_summary": int(self.has_compressed_summary),
        }

    def to_record(self) -> CheckpointRecord:
        return CheckpointRecord(
            id=self.id,
            task_id=self.task_id,
            run_id=self.run_id,
            created_at=self.created_at,
            storage_kind=self.storage_kind,
            blob_path=self.blob_path,
            blob_encoding=self.blob_encoding,
            payload_digest=self.payload_digest,
        )

    def to_summary(self) -> CheckpointSummary:
        return CheckpointSummary(
            id=self.id,
            task_id=self.task_id,
            run_id=self.run_id,
            created_at=self.created_at,
            storage_kind=self.storage_kind,
            payload_size_bytes=self.payload_size_bytes,
            history_message_count=self.history_message_count,
            history_text_bytes=self.history_text_bytes,
            has_compressed_summary=self.has_compressed_summary,
        )
