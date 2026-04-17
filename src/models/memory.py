from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


@dataclass(slots=True)
class MemoryEntry:
    id: str
    session_id: str
    source_job_id: str | None
    entry_type: str
    key: str
    value: Any
    summary: str
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        session_id: str | None = None,
        operation_id: str | None = None,
        entry_type: str,
        key: str,
        value: Any,
        summary: str,
        source_job_id: str | None = None,
    ) -> "MemoryEntry":
        resolved_session_id = session_id or operation_id
        if not resolved_session_id:
            raise ValueError("session_id is required.")
        return cls(
            id=str(uuid4()),
            session_id=resolved_session_id,
            source_job_id=source_job_id,
            entry_type=entry_type,
            key=key,
            value=value,
            summary=summary,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "MemoryEntry":
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            source_job_id=row["source_job_id"],
            entry_type=row["entry_type"],
            key=row["key"],
            value=json.loads(row["value"]) if row.get("value") else None,
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "source_job_id": self.source_job_id,
            "entry_type": self.entry_type,
            "key": self.key,
            "value": json.dumps(self.value, ensure_ascii=False),
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @property
    def operation_id(self) -> str:
        return self.session_id

    @operation_id.setter
    def operation_id(self, value: str) -> None:
        self.session_id = value
