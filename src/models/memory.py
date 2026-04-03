from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


@dataclass(slots=True)
class MemoryEntry:
    id: str
    operation_id: str
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
        operation_id: str,
        entry_type: str,
        key: str,
        value: Any,
        summary: str,
        source_job_id: str | None = None,
    ) -> "MemoryEntry":
        return cls(
            id=str(uuid4()),
            operation_id=operation_id,
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
            operation_id=row["operation_id"],
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
            "operation_id": self.operation_id,
            "source_job_id": self.source_job_id,
            "entry_type": self.entry_type,
            "key": self.key,
            "value": json.dumps(self.value, ensure_ascii=False),
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
