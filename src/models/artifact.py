from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


@dataclass(slots=True)
class Artifact:
    id: str
    public_id: str
    session_id: str
    source_job_id: str | None
    artifact_type: str
    target_ref: str
    title: str
    summary: str
    artifact_path: str | None = None
    content_type: str | None = None
    hash_digest: str | None = None
    captured_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        artifact_type: str,
        target_ref: str,
        title: str,
        summary: str,
        source_job_id: str | None = None,
        artifact_path: str | None = None,
        content_type: str | None = None,
        hash_digest: str | None = None,
        captured_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Artifact":
        return cls(
            id=str(uuid4()),
            public_id="",
            session_id=session_id,
            source_job_id=source_job_id,
            artifact_type=artifact_type,
            target_ref=target_ref,
            title=title,
            summary=summary,
            artifact_path=artifact_path,
            content_type=content_type,
            hash_digest=hash_digest,
            captured_at=captured_at or utc_now_iso(),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Artifact":
        raw_metadata = row.get("metadata")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            session_id=row["session_id"],
            source_job_id=row["source_job_id"],
            artifact_type=row["artifact_type"],
            target_ref=row["target_ref"],
            title=row["title"],
            summary=row["summary"],
            artifact_path=row["artifact_path"],
            content_type=row["content_type"],
            hash_digest=row["hash_digest"],
            captured_at=row["captured_at"],
            metadata=json.loads(raw_metadata) if raw_metadata else {},
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "session_id": self.session_id,
            "source_job_id": self.source_job_id,
            "artifact_type": self.artifact_type,
            "target_ref": self.target_ref,
            "title": self.title,
            "summary": self.summary,
            "artifact_path": self.artifact_path,
            "content_type": self.content_type,
            "hash_digest": self.hash_digest,
            "captured_at": self.captured_at,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }

    @property
    def evidence_type(self) -> str:
        return self.artifact_type

    @property
    def operation_id(self) -> str:
        return self.session_id

    @property
    def job_id(self) -> str | None:
        return self.source_job_id
