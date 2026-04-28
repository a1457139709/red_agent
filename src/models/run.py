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


class SessionLogLevel(StrEnum):
    INFO = "info"
    ERROR = "error"


@dataclass(slots=True, init=False)
class Run:
    id: str
    public_id: str
    session_id: str
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

    def __init__(
        self,
        *,
        id: str,
        public_id: str,
        session_id: str,
        status: RunStatus = RunStatus.RUNNING,
        started_at: str | None = None,
        finished_at: str | None = None,
        step_count: int = 0,
        last_usage: dict[str, Any] | None = None,
        last_error: str | None = None,
        duration_ms: int | None = None,
        effective_skill_name: str | None = None,
        effective_tools: list[str] | None = None,
        failure_kind: str | None = None,
    ) -> None:
        self.id = id
        self.public_id = public_id
        self.session_id = session_id
        self.status = RunStatus(status)
        self.started_at = started_at or utc_now_iso()
        self.finished_at = finished_at
        self.step_count = step_count
        self.last_usage = dict(last_usage or {})
        self.last_error = last_error
        self.duration_ms = duration_ms
        self.effective_skill_name = effective_skill_name
        self.effective_tools = list(effective_tools or [])
        self.failure_kind = failure_kind

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
    ) -> "Run":
        return cls(
            id=str(uuid4()),
            public_id="",
            session_id=session_id,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Run":
        raw_usage = row.get("last_usage")
        raw_tools = row.get("effective_tools")
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            session_id=row["session_id"],
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
            "session_id": self.session_id,
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
class SessionLogEntry:
    id: str
    session_id: str
    run_id: str | None
    level: SessionLogLevel
    message: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        level: SessionLogLevel,
        message: str,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "SessionLogEntry":
        return cls(
            id=str(uuid4()),
            session_id=session_id,
            run_id=run_id,
            level=level,
            message=message,
            payload=payload or {},
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "SessionLogEntry":
        raw_payload = row.get("payload")
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            level=SessionLogLevel(row["level"]),
            message=row["message"],
            payload=json.loads(raw_payload) if raw_payload else {},
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "level": self.level.value,
            "message": self.message,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "created_at": self.created_at,
        }
