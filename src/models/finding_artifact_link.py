from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from .run import utc_now_iso


@dataclass(slots=True)
class FindingArtifactLink:
    id: str
    session_id: str
    finding_id: str
    artifact_id: str
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        finding_id: str,
        artifact_id: str,
    ) -> "FindingArtifactLink":
        return cls(
            id=str(uuid4()),
            session_id=session_id,
            finding_id=finding_id,
            artifact_id=artifact_id,
        )

    @classmethod
    def from_row(cls, row: dict) -> "FindingArtifactLink":
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            finding_id=row["finding_id"],
            artifact_id=row["artifact_id"],
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "finding_id": self.finding_id,
            "artifact_id": self.artifact_id,
            "created_at": self.created_at,
        }
