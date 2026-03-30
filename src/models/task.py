from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Task:
    id: str
    public_id: str
    title: str
    goal: str
    workspace: str
    status: TaskStatus = TaskStatus.PENDING
    session_id: str | None = None
    skill_profile: str | None = None
    priority: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_checkpoint: str | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        title: str,
        goal: str,
        workspace: str,
        session_id: str | None = None,
        skill_profile: str | None = None,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> "Task":
        return cls(
            id=str(uuid4()),
            public_id="",
            title=title,
            goal=goal,
            workspace=workspace,
            session_id=session_id,
            skill_profile=skill_profile,
            priority=priority,
            metadata=metadata or {},
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Task":
        metadata = row.get("metadata")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            title=row["title"],
            goal=row["goal"],
            workspace=row["workspace"],
            status=TaskStatus(row["status"]),
            session_id=row["session_id"],
            skill_profile=row["skill_profile"],
            priority=row["priority"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_checkpoint=row["last_checkpoint"],
            last_error=row["last_error"],
            metadata=json.loads(metadata) if metadata else {},
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "title": self.title,
            "goal": self.goal,
            "workspace": self.workspace,
            "status": self.status.value,
            "session_id": self.session_id,
            "skill_profile": self.skill_profile,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_checkpoint": self.last_checkpoint,
            "last_error": self.last_error,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }

    def with_status(
        self,
        status: TaskStatus,
        *,
        last_checkpoint: str | None = None,
        last_error: str | None = None,
    ) -> "Task":
        return Task(
            id=self.id,
            public_id=self.public_id,
            title=self.title,
            goal=self.goal,
            workspace=self.workspace,
            status=status,
            session_id=self.session_id,
            skill_profile=self.skill_profile,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=utc_now_iso(),
            last_checkpoint=last_checkpoint if last_checkpoint is not None else self.last_checkpoint,
            last_error=last_error,
            metadata=dict(self.metadata),
        )
