from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from models.run import utc_now_iso


@dataclass(frozen=True, slots=True)
class ServerEventEnvelope:
    event_id: str
    project_id: str | None
    session_id: str | None
    task_id: str | None
    sequence: int
    event_kind: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        event_kind: str,
        payload: dict[str, Any] | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> "ServerEventEnvelope":
        return cls(
            event_id=str(uuid4()),
            project_id=project_id,
            session_id=session_id,
            task_id=task_id,
            sequence=sequence,
            event_kind=event_kind,
            timestamp=utc_now_iso(),
            payload=dict(payload or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
