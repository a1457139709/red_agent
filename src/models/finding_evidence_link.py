from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .run import utc_now_iso


@dataclass(slots=True)
class FindingEvidenceLink:
    id: str
    operation_id: str
    finding_id: str
    evidence_id: str
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        finding_id: str,
        evidence_id: str,
    ) -> "FindingEvidenceLink":
        return cls(
            id=str(uuid4()),
            operation_id=operation_id,
            finding_id=finding_id,
            evidence_id=evidence_id,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "FindingEvidenceLink":
        return cls(
            id=row["id"],
            operation_id=row["operation_id"],
            finding_id=row["finding_id"],
            evidence_id=row["evidence_id"],
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "finding_id": self.finding_id,
            "evidence_id": self.evidence_id,
            "created_at": self.created_at,
        }
