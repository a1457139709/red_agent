from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class JobLogLevel(StrEnum):
    INFO = "info"
    ERROR = "error"


@dataclass(slots=True)
class Job:
    id: str
    public_id: str
    operation_id: str
    job_type: str
    target_ref: str
    status: JobStatus = JobStatus.PENDING
    arguments: dict[str, Any] = field(default_factory=dict)
    dependency_job_ids: list[str] = field(default_factory=list)
    timeout_seconds: int | None = None
    retry_limit: int = 0
    retry_count: int = 0
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        job_type: str,
        target_ref: str,
        status: JobStatus = JobStatus.PENDING,
        arguments: dict[str, Any] | None = None,
        dependency_job_ids: list[str] | None = None,
        timeout_seconds: int | None = None,
        retry_limit: int = 0,
    ) -> "Job":
        return cls(
            id=str(uuid4()),
            public_id="",
            operation_id=operation_id,
            job_type=job_type,
            target_ref=target_ref,
            status=status,
            arguments=dict(arguments or {}),
            dependency_job_ids=list(dependency_job_ids or []),
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Job":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            operation_id=row["operation_id"],
            job_type=row["job_type"],
            target_ref=row["target_ref"],
            status=JobStatus(row["status"]),
            arguments=json.loads(row["arguments"]) if row.get("arguments") else {},
            dependency_job_ids=json.loads(row["dependency_job_ids"])
            if row.get("dependency_job_ids")
            else [],
            timeout_seconds=row["timeout_seconds"],
            retry_limit=row["retry_limit"],
            retry_count=row["retry_count"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "operation_id": self.operation_id,
            "job_type": self.job_type,
            "target_ref": self.target_ref,
            "status": self.status.value,
            "arguments": json.dumps(self.arguments, ensure_ascii=False),
            "dependency_job_ids": json.dumps(self.dependency_job_ids, ensure_ascii=False),
            "timeout_seconds": self.timeout_seconds,
            "retry_limit": self.retry_limit,
            "retry_count": self.retry_count,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class JobLogEntry:
    id: str
    job_id: str
    level: JobLogLevel
    message: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        level: JobLogLevel,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> "JobLogEntry":
        return cls(
            id=str(uuid4()),
            job_id=job_id,
            level=level,
            message=message,
            payload=payload or {},
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "JobLogEntry":
        return cls(
            id=row["id"],
            job_id=row["job_id"],
            level=JobLogLevel(row["level"]),
            message=row["message"],
            payload=json.loads(row["payload"]) if row.get("payload") else {},
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "level": self.level.value,
            "message": self.message,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "created_at": self.created_at,
        }
