from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


@dataclass(slots=True)
class Report:
    id: str
    public_id: str
    session_id: str
    report_type: str
    title: str
    summary: str
    artifact_path: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        report_type: str,
        title: str,
        summary: str,
        artifact_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Report":
        return cls(
            id=str(uuid4()),
            public_id="",
            session_id=session_id,
            report_type=report_type,
            title=title,
            summary=summary,
            artifact_path=artifact_path,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Report":
        raw_metadata = row.get("metadata")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            session_id=row["session_id"],
            report_type=row["report_type"],
            title=row["title"],
            summary=row["summary"],
            artifact_path=row["artifact_path"],
            created_at=row["created_at"],
            metadata=json.loads(raw_metadata) if raw_metadata else {},
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "session_id": self.session_id,
            "report_type": self.report_type,
            "title": self.title,
            "summary": self.summary,
            "artifact_path": self.artifact_path,
            "created_at": self.created_at,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }
