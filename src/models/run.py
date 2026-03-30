from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def duration_ms_between(started_at: str, finished_at: str | None) -> int | None:
    if finished_at is None:
        return None
    started = datetime.fromisoformat(started_at)
    finished = datetime.fromisoformat(finished_at)
    return max(0, int((finished - started).total_seconds() * 1000))


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunFailureKind(StrEnum):
    SKILL_RESOLUTION_ERROR = "skill_resolution_error"
    POLICY_DENIED = "policy_denied"
    TOOL_ERROR = "tool_error"
    MODEL_ERROR = "model_error"
    RUNTIME_ERROR = "runtime_error"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"


class TaskLogLevel(StrEnum):
    INFO = "info"
    ERROR = "error"


@dataclass(slots=True)
class Run:
    id: str
    public_id: str
    task_id: str
    status: RunStatus = RunStatus.RUNNING
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    step_count: int = 0
    last_usage: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    duration_ms: int | None = None
    effective_skill_name: str | None = None
    effective_tools: list[str] = field(default_factory=list)
    failure_kind: str | None = None

    @classmethod
    def create(cls, *, task_id: str) -> "Run":
        return cls(
            id=str(uuid4()),
            public_id="",
            task_id=task_id,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Run":
        raw_usage = row.get("last_usage")
        raw_tools = row.get("effective_tools")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            task_id=row["task_id"],
            status=RunStatus(row["status"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            step_count=row["step_count"],
            last_usage=json.loads(raw_usage) if raw_usage else {},
            last_error=row["last_error"],
            duration_ms=row.get("duration_ms"),
            effective_skill_name=row.get("effective_skill_name"),
            effective_tools=json.loads(raw_tools) if raw_tools else [],
            failure_kind=row.get("failure_kind"),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "step_count": self.step_count,
            "last_usage": json.dumps(self.last_usage, ensure_ascii=False),
            "last_error": self.last_error,
            "duration_ms": self.duration_ms,
            "effective_skill_name": self.effective_skill_name,
            "effective_tools": json.dumps(self.effective_tools, ensure_ascii=False),
            "failure_kind": self.failure_kind,
        }


@dataclass(slots=True)
class Checkpoint:
    id: str
    task_id: str
    run_id: str | None
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        payload: dict[str, Any],
        run_id: str | None = None,
    ) -> "Checkpoint":
        return cls(
            id=str(uuid4()),
            task_id=task_id,
            run_id=run_id,
            payload=payload,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Checkpoint":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row["run_id"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class TaskLogEntry:
    id: str
    task_id: str
    run_id: str | None
    level: TaskLogLevel
    message: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        level: TaskLogLevel,
        message: str,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "TaskLogEntry":
        return cls(
            id=str(uuid4()),
            task_id=task_id,
            run_id=run_id,
            level=level,
            message=message,
            payload=payload or {},
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TaskLogEntry":
        raw_payload = row.get("payload")
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row["run_id"],
            level=TaskLogLevel(row["level"]),
            message=row["message"],
            payload=json.loads(raw_payload) if raw_payload else {},
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "level": self.level.value,
            "message": self.message,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "created_at": self.created_at,
        }
