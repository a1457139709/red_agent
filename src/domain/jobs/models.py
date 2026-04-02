from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from domain.common import json_dumps, json_loads, utc_now_iso


class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass(slots=True)
class Job:
    id: str
    public_id: str
    operation_id: str
    planner_run_id: str | None
    parent_job_id: str | None
    job_type: str
    tool_name: str
    target_ref: str
    status: JobStatus = JobStatus.PENDING
    priority: int = 100
    args: dict[str, Any] = field(default_factory=dict)
    result_summary: str | None = None
    timeout_seconds: int = 300
    max_retries: int = 0
    retry_count: int = 0
    worker_id: str | None = None
    lease_expires_at: str | None = None
    queued_at: str | None = None
    started_at: str | None = None
    heartbeat_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        job_type: str,
        tool_name: str,
        target_ref: str,
        planner_run_id: str | None = None,
        parent_job_id: str | None = None,
        status: JobStatus = JobStatus.PENDING,
        priority: int = 100,
        args: dict[str, Any] | None = None,
        timeout_seconds: int = 300,
        max_retries: int = 0,
    ) -> "Job":
        return cls(
            id=str(uuid4()),
            public_id="",
            operation_id=operation_id,
            planner_run_id=planner_run_id,
            parent_job_id=parent_job_id,
            job_type=job_type,
            tool_name=tool_name,
            target_ref=target_ref,
            status=status,
            priority=priority,
            args=args or {},
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Job":
        return cls(
            id=row["id"],
            public_id=row["public_id"],
            operation_id=row["operation_id"],
            planner_run_id=row["planner_run_id"],
            parent_job_id=row["parent_job_id"],
            job_type=row["job_type"],
            tool_name=row["tool_name"],
            target_ref=row["target_ref"],
            status=JobStatus(row["status"]),
            priority=row["priority"],
            args=json_loads(row["args_json"], {}),
            result_summary=row["result_summary"],
            timeout_seconds=row["timeout_seconds"],
            max_retries=row["max_retries"],
            retry_count=row["retry_count"],
            worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            heartbeat_at=row["heartbeat_at"],
            finished_at=row["finished_at"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "operation_id": self.operation_id,
            "planner_run_id": self.planner_run_id,
            "parent_job_id": self.parent_job_id,
            "job_type": self.job_type,
            "tool_name": self.tool_name,
            "target_ref": self.target_ref,
            "status": self.status.value,
            "priority": self.priority,
            "args_json": json_dumps(self.args),
            "result_summary": self.result_summary,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "worker_id": self.worker_id,
            "lease_expires_at": self.lease_expires_at,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "heartbeat_at": self.heartbeat_at,
            "finished_at": self.finished_at,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
