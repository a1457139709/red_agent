from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


class OperationEventType(StrEnum):
    ADMISSION_REQUESTED = "admission_requested"
    ADMISSION_DENIED = "admission_denied"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMATION_APPROVED = "confirmation_approved"
    CONFIRMATION_DENIED = "confirmation_denied"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"


class OperationEventLevel(StrEnum):
    INFO = "info"
    ERROR = "error"


@dataclass(slots=True)
class OperationEvent:
    id: str
    operation_id: str
    job_id: str | None
    event_type: OperationEventType
    level: OperationEventLevel
    tool_name: str
    tool_category: str
    target_ref: str
    reason_code: str | None = None
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        event_type: OperationEventType,
        level: OperationEventLevel,
        tool_name: str,
        tool_category: str,
        target_ref: str,
        job_id: str | None = None,
        reason_code: str | None = None,
        message: str = "",
        payload: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> "OperationEvent":
        return cls(
            id=str(uuid4()),
            operation_id=operation_id,
            job_id=job_id,
            event_type=event_type,
            level=level,
            tool_name=tool_name,
            tool_category=tool_category,
            target_ref=target_ref,
            reason_code=reason_code,
            message=message,
            payload=payload or {},
            created_at=created_at or utc_now_iso(),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "OperationEvent":
        raw_payload = row.get("payload")
        return cls(
            id=row["id"],
            operation_id=row["operation_id"],
            job_id=row["job_id"],
            event_type=OperationEventType(row["event_type"]),
            level=OperationEventLevel(row["level"]),
            tool_name=row["tool_name"],
            tool_category=row["tool_category"],
            target_ref=row["target_ref"],
            reason_code=row["reason_code"],
            message=row["message"],
            payload=json.loads(raw_payload) if raw_payload else {},
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "job_id": self.job_id,
            "event_type": self.event_type.value,
            "level": self.level.value,
            "tool_name": self.tool_name,
            "tool_category": self.tool_category,
            "target_ref": self.target_ref,
            "reason_code": self.reason_code,
            "message": self.message,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "created_at": self.created_at,
        }
