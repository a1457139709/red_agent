from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4

from models.session import Session, SessionMode, SessionStatus


class ControllerIntent(StrEnum):
    NORMAL_REQUEST = "normal_request"
    REDTEAM_REQUEST = "redteam_request"
    RECORD_LOOKUP_REQUEST = "record_lookup_request"
    ADVANCED_COMMAND_REQUEST = "advanced_command_request"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED_REQUEST = "unsupported_request"


class ControllerResultStatus(StrEnum):
    HANDLED = "handled"
    CLARIFICATION_REQUIRED = "clarification_required"
    DELEGATED_TO_ADVANCED_COMMAND = "delegated_to_advanced_command"
    UNSUPPORTED = "unsupported"


class ClarificationKind(StrEnum):
    BARE_TARGET = "bare_target"
    MISSING_TARGET = "missing_target"
    PERSISTENCE_MODE = "persistence_mode"
    RECORD_SCOPE = "record_scope"


class ExecutionBridgeKind(StrEnum):
    BASE_RUNTIME = "base_runtime"
    ACTIVE_SKILL_RUNTIME = "active_skill_runtime"


@dataclass(slots=True)
class SessionSummary:
    id: str
    public_id: str
    title: str
    mode: SessionMode
    status: SessionStatus
    target_summary: str | None
    reused: bool = False

    @classmethod
    def from_session(cls, session: Session, *, reused: bool) -> "SessionSummary":
        return cls(
            id=session.id,
            public_id=session.public_id,
            title=session.title,
            mode=session.mode,
            status=session.status,
            target_summary=session.target_summary,
            reused=reused,
        )


@dataclass(slots=True)
class ClarificationRequest:
    kind: ClarificationKind
    question: str
    missing_fields: list[str]
    original_request: str
    context: dict[str, str] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(slots=True)
class ClarificationAnswer:
    request_id: str
    kind: ClarificationKind
    raw_answer: str


@dataclass(slots=True)
class ExecutionBridge:
    kind: ExecutionBridgeKind
    prompt_text: str


@dataclass(slots=True)
class ControllerRequest:
    raw_input: str
    active_skill_name: str | None = None
    active_session_id: str | None = None
    active_session_public_id: str | None = None
    active_session_mode: SessionMode | None = None
    active_session_title: str | None = None
    active_session_target_summary: str | None = None
    pending_clarification: ClarificationRequest | None = None

    @property
    def is_slash_command(self) -> bool:
        return self.raw_input.strip().startswith("/")


@dataclass(slots=True)
class ControllerResult:
    status: ControllerResultStatus
    intent: ControllerIntent
    message: str | None = None
    session_summary: SessionSummary | None = None
    clarification_request: ClarificationRequest | None = None
    execution_bridge: ExecutionBridge | None = None
    bind_session: bool = False

    @classmethod
    def handled(
        cls,
        *,
        intent: ControllerIntent,
        message: str | None = None,
        session_summary: SessionSummary | None = None,
        execution_bridge: ExecutionBridge | None = None,
        bind_session: bool = False,
    ) -> "ControllerResult":
        return cls(
            status=ControllerResultStatus.HANDLED,
            intent=intent,
            message=message,
            session_summary=session_summary,
            execution_bridge=execution_bridge,
            bind_session=bind_session,
        )

    @classmethod
    def clarification_required(
        cls,
        *,
        message: str | None,
        clarification_request: ClarificationRequest,
    ) -> "ControllerResult":
        return cls(
            status=ControllerResultStatus.CLARIFICATION_REQUIRED,
            intent=ControllerIntent.CLARIFICATION_REQUIRED,
            message=message,
            clarification_request=clarification_request,
        )

    @classmethod
    def delegated_to_advanced_command(
        cls,
        *,
        message: str | None = None,
    ) -> "ControllerResult":
        return cls(
            status=ControllerResultStatus.DELEGATED_TO_ADVANCED_COMMAND,
            intent=ControllerIntent.ADVANCED_COMMAND_REQUEST,
            message=message,
        )

    @classmethod
    def unsupported(
        cls,
        *,
        message: str,
    ) -> "ControllerResult":
        return cls(
            status=ControllerResultStatus.UNSUPPORTED,
            intent=ControllerIntent.UNSUPPORTED_REQUEST,
            message=message,
        )
