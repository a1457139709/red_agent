from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


class SessionMode(StrEnum):
    NORMAL = "normal"
    REDTEAM = "redteam"


class SessionPersistenceMode(StrEnum):
    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class SessionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionTargetKind(StrEnum):
    DOMAIN = "domain"
    HOST = "host"
    IP = "ip"
    CIDR = "cidr"
    URL = "url"


TERMINAL_SESSION_STATUSES = frozenset(
    {
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    }
)

ALLOWED_SESSION_STATUS_TRANSITIONS = {
    SessionStatus.DRAFT: {
        SessionStatus.ACTIVE,
        SessionStatus.CANCELLED,
    },
    SessionStatus.ACTIVE: {
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    },
    SessionStatus.PAUSED: {
        SessionStatus.ACTIVE,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    },
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
    SessionStatus.CANCELLED: set(),
}


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(slots=True)
class SessionTarget:
    kind: SessionTargetKind
    value: str
    note: str | None = None

    def __post_init__(self) -> None:
        self.kind = SessionTargetKind(self.kind)
        self.value = _normalize_required_text(self.value, field_name="target value")
        self.note = _normalize_optional_text(self.note)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionTarget":
        return cls(
            kind=payload["kind"],
            value=payload["value"],
            note=payload.get("note"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "value": self.value,
            "note": self.note,
        }


@dataclass(slots=True)
class Session:
    id: str
    public_id: str
    title: str
    goal: str
    mode: SessionMode
    persistence_mode: SessionPersistenceMode
    workspace: str
    status: SessionStatus = SessionStatus.DRAFT
    targets: list[SessionTarget] = field(default_factory=list)
    target_summary: str | None = None
    authorization_note: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    closed_at: str | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = _normalize_required_text(self.title, field_name="title")
        self.goal = _normalize_required_text(self.goal, field_name="goal")
        self.workspace = _normalize_required_text(self.workspace, field_name="workspace")
        self.mode = SessionMode(self.mode)
        self.persistence_mode = SessionPersistenceMode(self.persistence_mode)
        self.status = SessionStatus(self.status)
        self.targets = [self._coerce_target(target) for target in self.targets]
        self.target_summary = _normalize_optional_text(self.target_summary)
        if self.target_summary is None:
            self.target_summary = self.derive_target_summary(self.targets)
        self.authorization_note = _normalize_optional_text(self.authorization_note)
        self.last_error = _normalize_optional_text(self.last_error)
        self.metadata = dict(self.metadata)

    @classmethod
    def create(
        cls,
        *,
        title: str,
        goal: str,
        mode: SessionMode,
        persistence_mode: SessionPersistenceMode,
        workspace: str,
        status: SessionStatus = SessionStatus.DRAFT,
        targets: list[SessionTarget] | None = None,
        target_summary: str | None = None,
        authorization_note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Session":
        return cls(
            id=str(uuid4()),
            public_id="",
            title=title,
            goal=goal,
            mode=mode,
            persistence_mode=persistence_mode,
            workspace=workspace,
            status=status,
            targets=list(targets or []),
            target_summary=target_summary,
            authorization_note=authorization_note,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Session":
        raw_targets = row.get("targets_json")
        raw_metadata = row.get("metadata")
        targets_payload = json.loads(raw_targets) if raw_targets else []
        metadata = json.loads(raw_metadata) if raw_metadata else {}
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            title=row["title"],
            goal=row["goal"],
            mode=row["mode"],
            persistence_mode=row["persistence_mode"],
            workspace=row["workspace"],
            status=row["status"],
            targets=[SessionTarget.from_dict(item) for item in targets_payload],
            target_summary=row.get("target_summary"),
            authorization_note=row.get("authorization_note"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row.get("closed_at"),
            last_error=row.get("last_error"),
            metadata=metadata,
        )

    @staticmethod
    def derive_target_summary(targets: list[SessionTarget]) -> str | None:
        if not targets:
            return None
        values = [target.value for target in targets]
        preview = values[:3]
        summary = ", ".join(preview)
        if len(values) > 3:
            summary = f"{summary}, +{len(values) - 3} more"
        return summary

    @staticmethod
    def can_transition(current: SessionStatus, target: SessionStatus) -> bool:
        if current == target:
            return True
        return target in ALLOWED_SESSION_STATUS_TRANSITIONS[SessionStatus(current)]

    @staticmethod
    def require_valid_transition(current: SessionStatus, target: SessionStatus) -> None:
        current_status = SessionStatus(current)
        target_status = SessionStatus(target)
        if not Session.can_transition(current_status, target_status):
            raise ValueError(
                f"Invalid session status transition: {current_status.value} -> {target_status.value}."
            )

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_SESSION_STATUSES

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "title": self.title,
            "goal": self.goal,
            "mode": self.mode.value,
            "persistence_mode": self.persistence_mode.value,
            "workspace": self.workspace,
            "status": self.status.value,
            "target_summary": self.target_summary,
            "authorization_note": self.authorization_note,
            "targets_json": json.dumps(
                [target.to_dict() for target in self.targets],
                ensure_ascii=False,
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "last_error": self.last_error,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }

    @staticmethod
    def _coerce_target(target: SessionTarget | dict[str, Any]) -> SessionTarget:
        if isinstance(target, SessionTarget):
            return target
        if isinstance(target, dict):
            return SessionTarget.from_dict(target)
        raise ValueError("targets must contain SessionTarget items.")
