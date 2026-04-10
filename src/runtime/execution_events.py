from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from models.run import utc_now_iso


class ExecutionEventType(StrEnum):
    EXECUTION_STARTED = "execution_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMATION_APPROVED = "confirmation_approved"
    CONFIRMATION_DENIED = "confirmation_denied"
    EXECUTION_PAUSED = "execution_paused"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"


@dataclass(slots=True)
class ExecutionProgressEvent:
    event_type: ExecutionEventType
    session_id: str
    session_public_id: str
    step_type: str | None = None
    step_label: str | None = None
    target_summary: str | None = None
    message: str | None = None
    action_name: str | None = None
    risk_level: str | None = None
    reason: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "session_public_id": self.session_public_id,
            "step_type": self.step_type,
            "step_label": self.step_label,
            "target_summary": self.target_summary,
            "message": self.message,
            "action_name": self.action_name,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ExecutionOutcome:
    status: str
    response: str
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw_result: dict[str, Any] | None = None

    @property
    def is_completed(self) -> bool:
        return self.status == "completed" and self.error is None
