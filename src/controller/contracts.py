from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4

from app.session_record_query_service import (
    ExecutionStepView,
    FindingExplanationTraceView,
    SessionHistorySummaryView,
)
from models.artifact import Artifact
from models.finding import Finding
from models.report import Report
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


class RecordLookupKind(StrEnum):
    SESSION_HISTORY = "session_history"
    EXECUTION_STEPS = "execution_steps"
    ARTIFACTS = "artifacts"
    FINDINGS = "findings"
    REPORTS = "reports"
    FINDING_EXPLANATION = "finding_explanation"


class ReportType(StrEnum):
    SESSION_SUMMARY = "session_summary"
    FINDINGS_SUMMARY = "findings_summary"
    OPERATOR_REPORT = "operator_report"


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
class RecordQueryRequest:
    kind: RecordLookupKind
    explicit_scope: str | None = None
    lookup_identifier: str | None = None
    report_type: ReportType | None = None
    source_command: str | None = None

    def __post_init__(self) -> None:
        self.kind = RecordLookupKind(self.kind)
        if self.explicit_scope is not None:
            normalized_scope = self.explicit_scope.strip()
            self.explicit_scope = normalized_scope or None
        if self.lookup_identifier is not None:
            normalized_identifier = self.lookup_identifier.strip().upper()
            self.lookup_identifier = normalized_identifier or None
        if self.report_type is not None:
            self.report_type = ReportType(self.report_type)
        if self.source_command is not None:
            normalized_command = self.source_command.strip().lower()
            self.source_command = normalized_command or None

    @property
    def requests_report_generation(self) -> bool:
        return self.report_type is not None


@dataclass(slots=True)
class RecordLookupPayload:
    session_summary: SessionSummary
    query: RecordQueryRequest
    resolved_scope: str
    history_summary: SessionHistorySummaryView | None = None
    execution_steps: list[ExecutionStepView] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    reports: list[Report] = field(default_factory=list)


@dataclass(slots=True)
class FindingExplanationPayload:
    session_summary: SessionSummary
    query: RecordQueryRequest
    resolved_scope: str
    finding_identifier: str
    explanation: FindingExplanationTraceView | None = None


@dataclass(slots=True)
class GeneratedReportPayload:
    session_summary: SessionSummary
    query: RecordQueryRequest
    resolved_scope: str
    report_type: ReportType
    report: Report | None = None
    reused: bool = False
    linked_artifact_ids: list[str] = field(default_factory=list)
    linked_finding_ids: list[str] = field(default_factory=list)


class ConfirmationDecisionValue(StrEnum):
    APPROVE = "approve"
    DENY = "deny"


@dataclass(slots=True)
class ConfirmationRequest:
    action_name: str
    risk_level: str
    target_summary: str | None
    reason: str
    message: str
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(slots=True)
class ConfirmationDecision:
    request_id: str
    decision: ConfirmationDecisionValue


@dataclass(slots=True)
class ControllerRequest:
    raw_input: str
    record_query: RecordQueryRequest | None = None
    active_skill_name: str | None = None
    requested_session_mode: SessionMode = SessionMode.NORMAL
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
    record_lookup_payload: RecordLookupPayload | None = None
    finding_explanation_payload: FindingExplanationPayload | None = None
    generated_report_payload: GeneratedReportPayload | None = None
    clarification_request: ClarificationRequest | None = None
    confirmation_request: ConfirmationRequest | None = None
    execution_bridge: ExecutionBridge | None = None
    bind_session: bool = False

    @classmethod
    def handled(
        cls,
        *,
        intent: ControllerIntent,
        message: str | None = None,
        session_summary: SessionSummary | None = None,
        record_lookup_payload: RecordLookupPayload | None = None,
        finding_explanation_payload: FindingExplanationPayload | None = None,
        generated_report_payload: GeneratedReportPayload | None = None,
        execution_bridge: ExecutionBridge | None = None,
        bind_session: bool = False,
    ) -> "ControllerResult":
        return cls(
            status=ControllerResultStatus.HANDLED,
            intent=intent,
            message=message,
            session_summary=session_summary,
            record_lookup_payload=record_lookup_payload,
            finding_explanation_payload=finding_explanation_payload,
            generated_report_payload=generated_report_payload,
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
