from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .run import utc_now_iso


class FindingStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    DUPLICATE = "duplicate"
    FIXED = "fixed"


@dataclass(slots=True)
class Finding:
    id: str
    public_id: str
    operation_id: str
    source_job_id: str | None
    finding_type: str
    title: str
    target_ref: str
    severity: str
    confidence: str
    status: FindingStatus = FindingStatus.OPEN
    summary: str = ""
    impact: str = ""
    reproduction_notes: str = ""
    next_action: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        finding_type: str,
        title: str,
        target_ref: str,
        severity: str,
        confidence: str,
        source_job_id: str | None = None,
        status: FindingStatus = FindingStatus.OPEN,
        summary: str = "",
        impact: str = "",
        reproduction_notes: str = "",
        next_action: str = "",
    ) -> "Finding":
        return cls(
            id=str(uuid4()),
            public_id="",
            operation_id=operation_id,
            source_job_id=source_job_id,
            finding_type=finding_type,
            title=title,
            target_ref=target_ref,
            severity=severity,
            confidence=confidence,
            status=status,
            summary=summary,
            impact=impact,
            reproduction_notes=reproduction_notes,
            next_action=next_action,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Finding":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            operation_id=row["operation_id"],
            source_job_id=row["source_job_id"],
            finding_type=row["finding_type"],
            title=row["title"],
            target_ref=row["target_ref"],
            severity=row["severity"],
            confidence=row["confidence"],
            status=FindingStatus(row["status"]),
            summary=row["summary"],
            impact=row["impact"],
            reproduction_notes=row["reproduction_notes"],
            next_action=row["next_action"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "operation_id": self.operation_id,
            "source_job_id": self.source_job_id,
            "finding_type": self.finding_type,
            "title": self.title,
            "target_ref": self.target_ref,
            "severity": self.severity,
            "confidence": self.confidence,
            "status": self.status.value,
            "summary": self.summary,
            "impact": self.impact,
            "reproduction_notes": self.reproduction_notes,
            "next_action": self.next_action,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
