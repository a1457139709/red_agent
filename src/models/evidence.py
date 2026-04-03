from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .run import utc_now_iso


@dataclass(slots=True)
class Evidence:
    id: str
    public_id: str
    operation_id: str
    job_id: str | None
    evidence_type: str
    target_ref: str
    title: str
    summary: str
    artifact_path: str | None = None
    content_type: str | None = None
    hash_digest: str | None = None
    captured_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        evidence_type: str,
        target_ref: str,
        title: str,
        summary: str,
        job_id: str | None = None,
        artifact_path: str | None = None,
        content_type: str | None = None,
        hash_digest: str | None = None,
        captured_at: str | None = None,
    ) -> "Evidence":
        return cls(
            id=str(uuid4()),
            public_id="",
            operation_id=operation_id,
            job_id=job_id,
            evidence_type=evidence_type,
            target_ref=target_ref,
            title=title,
            summary=summary,
            artifact_path=artifact_path,
            content_type=content_type,
            hash_digest=hash_digest,
            captured_at=captured_at or utc_now_iso(),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Evidence":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            operation_id=row["operation_id"],
            job_id=row["job_id"],
            evidence_type=row["evidence_type"],
            target_ref=row["target_ref"],
            title=row["title"],
            summary=row["summary"],
            artifact_path=row["artifact_path"],
            content_type=row["content_type"],
            hash_digest=row["hash_digest"],
            captured_at=row["captured_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "operation_id": self.operation_id,
            "job_id": self.job_id,
            "evidence_type": self.evidence_type,
            "target_ref": self.target_ref,
            "title": self.title,
            "summary": self.summary,
            "artifact_path": self.artifact_path,
            "content_type": self.content_type,
            "hash_digest": self.hash_digest,
            "captured_at": self.captured_at,
        }
