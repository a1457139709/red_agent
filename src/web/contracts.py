from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class WebEventKind(StrEnum):
    CONTROLLER_RESULT = "controller_result"
    EXECUTION_PROGRESS = "execution_progress"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMATION_RESOLVED = "confirmation_resolved"
    FINAL_ANSWER = "final_answer"
    INTERACTION_ERROR = "interaction_error"


@dataclass(frozen=True, slots=True)
class ConversationSnapshotDto:
    conversation_id: str
    active_skill_name: str | None
    requested_session_mode: str
    active_session_id: str | None
    active_session_public_id: str | None
    active_session_mode: str | None
    active_session_title: str | None
    active_session_target_summary: str | None


@dataclass(frozen=True, slots=True)
class MissingFieldErrorDto:
    message: str
    missing_fields: list[str] = field(default_factory=list)
    allowed_values: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionSummaryDto:
    id: str
    public_id: str
    title: str
    mode: str
    status: str
    target_summary: str | None
    reused: bool


@dataclass(frozen=True, slots=True)
class SessionHistoryDto:
    scope: str
    counts: dict[str, int]
    recent_runs: list[str] = field(default_factory=list)
    recent_jobs: list[str] = field(default_factory=list)
    recent_artifacts: list[str] = field(default_factory=list)
    recent_findings: list[str] = field(default_factory=list)
    recent_reports: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ExecutionStepDto:
    source_type: str
    occurred_at: str
    title: str
    detail: str
    status: str | None = None
    level: str | None = None
    run_public_id: str | None = None
    job_public_id: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactDto:
    id: str
    public_id: str
    artifact_type: str
    title: str
    summary: str
    target_ref: str | None
    source_job_id: str | None
    created_at: str
    artifact_path: str | None = None
    content_type: str | None = None
    hash_digest: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FindingDto:
    id: str
    public_id: str
    finding_type: str
    title: str
    target_ref: str
    severity: str
    confidence: str
    status: str
    summary: str
    source_job_id: str | None
    created_at: str
    impact: str = ""
    reproduction_notes: str = ""
    next_action: str = ""


@dataclass(frozen=True, slots=True)
class SessionEventDto:
    id: str
    event_type: str
    level: str
    message: str | None
    target_ref: str | None
    tool_name: str | None
    created_at: str
    job_id: str | None = None
    tool_category: str | None = None
    reason_code: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FindingExplanationDto:
    finding: FindingDto
    linked_artifacts: list[ArtifactDto] = field(default_factory=list)
    source_job_id: str | None = None
    supporting_job_ids: list[str] = field(default_factory=list)
    related_events: list[SessionEventDto] = field(default_factory=list)
    related_run_ids: list[str] = field(default_factory=list)
    missing_segments: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReportDto:
    id: str
    public_id: str
    report_type: str
    title: str
    summary: str
    created_at: str
    artifact_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GeneratedReportDto:
    scope: str
    report_type: str
    reused: bool
    report: ReportDto | None
    linked_artifact_ids: list[str] = field(default_factory=list)
    linked_finding_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DashboardDto:
    session: SessionSummaryDto
    policy: dict[str, Any]
    job_counts: dict[str, int]
    flagged_job_ids: list[str]
    finding_counts: dict[str, int]
    recent_findings: list[FindingDto]
    artifact_count: int
    recent_artifacts: list[ArtifactDto]
    report_count: int
    event_counts: dict[str, int]
    recent_events: list[SessionEventDto]


@dataclass(frozen=True, slots=True)
class ConfirmationRequestDto:
    request_id: str
    action_name: str
    risk_level: str
    target_summary: str | None
    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class ConfirmationDecisionDto:
    request_id: str
    decision: str


@dataclass(frozen=True, slots=True)
class ToolPresentationDto:
    title: str | None = None
    group: str | None = None
    accent: str | None = None


@dataclass(frozen=True, slots=True)
class ToolResultEnvelopeDto:
    summary: str
    model_text: str
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    presentation: ToolPresentationDto | None = None


@dataclass(frozen=True, slots=True)
class ToolEventDto:
    event_type: str
    tool_name: str
    capability: str | None = None
    target: str | None = None
    args_summary: str | None = None
    result_summary: str | None = None
    error: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    output: ToolResultEnvelopeDto | None = None


@dataclass(frozen=True, slots=True)
class ExecutionProgressDto:
    event_type: str
    session_id: str
    session_public_id: str
    step_type: str | None = None
    step_label: str | None = None
    target_summary: str | None = None
    message: str | None = None
    action_name: str | None = None
    risk_level: str | None = None
    reason: str | None = None
    timestamp: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    tool_event: ToolEventDto | None = None


@dataclass(frozen=True, slots=True)
class ControllerResultDto:
    status: str
    intent: str
    message: str | None
    bind_session: bool
    session_summary: SessionSummaryDto | None = None
    missing_field_error: MissingFieldErrorDto | None = None
    record_lookup: dict[str, Any] | None = None
    finding_explanation: FindingExplanationDto | None = None
    generated_report: GeneratedReportDto | None = None


@dataclass(frozen=True, slots=True)
class ConversationEventEnvelopeDto:
    conversation_id: str
    sequence: int
    event_kind: str
    session_id: str | None
    session_public_id: str | None
    timestamp: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ConversationMessageRequestDto:
    conversation_id: str
    raw_input: str


@dataclass(frozen=True, slots=True)
class ConversationMessageResponseDto:
    conversation: ConversationSnapshotDto
    controller_result: ControllerResultDto | None
    events: list[ConversationEventEnvelopeDto] = field(default_factory=list)
    final_text: str | None = None
    error_message: str | None = None
