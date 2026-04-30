from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from controller.contracts import SessionSummary
from models.session import SessionMode


@dataclass(slots=True)
class ConversationContext:
    conversation_id: str = field(default_factory=lambda: str(uuid4()))
    active_skill_name: str | None = None
    requested_session_mode: SessionMode = SessionMode.NORMAL
    active_session_id: str | None = None
    active_session_public_id: str | None = None
    active_session_mode: SessionMode | None = None
    active_session_title: str | None = None
    active_session_target_summary: str | None = None

    def active_session_label(self) -> str | None:
        if self.active_session_public_id:
            return self.active_session_public_id
        return self.active_session_id

    def bind_session(self, summary: SessionSummary) -> None:
        self.active_session_id = summary.id
        self.active_session_public_id = summary.public_id
        self.active_session_mode = summary.mode
        self.active_session_title = summary.title
        self.active_session_target_summary = summary.target_summary

    def clear_active_session(self) -> None:
        self.active_session_id = None
        self.active_session_public_id = None
        self.active_session_mode = None
        self.active_session_title = None
        self.active_session_target_summary = None

    def set_requested_session_mode(self, mode: SessionMode) -> None:
        self.requested_session_mode = SessionMode(mode)
