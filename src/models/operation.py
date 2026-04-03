from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .run import utc_now_iso


class OperationStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Operation:
    id: str
    public_id: str
    title: str
    objective: str
    workspace: str
    scope_policy_id: str
    status: OperationStatus = OperationStatus.DRAFT
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    closed_at: str | None = None
    last_error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        objective: str,
        workspace: str,
        scope_policy_id: str,
        status: OperationStatus = OperationStatus.DRAFT,
    ) -> "Operation":
        return cls(
            id=str(uuid4()),
            public_id="",
            title=title,
            objective=objective,
            workspace=workspace,
            scope_policy_id=scope_policy_id,
            status=status,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Operation":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            title=row["title"],
            objective=row["objective"],
            workspace=row["workspace"],
            scope_policy_id=row["scope_policy_id"],
            status=OperationStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            last_error=row["last_error"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "title": self.title,
            "objective": self.objective,
            "workspace": self.workspace,
            "scope_policy_id": self.scope_policy_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "last_error": self.last_error,
        }
