from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.dashboard_service import SessionDashboard
from app.session_record_query_service import (
    ExecutionStepView,
    FindingExplanationTraceView,
    SessionHistorySummaryView,
)
from controller.contracts import (
    ClarificationRequest,
    ConfirmationDecision,
    ConfirmationRequest,
    ControllerResult,
    GeneratedReportPayload,
    RecordLookupPayload,
    SessionSummary,
)
from models.artifact import Artifact
from models.conversation_context import ConversationContext
from models.finding import Finding
from models.report import Report
from models.session_event import SessionEvent
from runtime.execution_events import ExecutionProgressEvent

from .contracts import (
    ArtifactDto,
    ClarificationRequestDto,
    ConfirmationDecisionDto,
    ConfirmationRequestDto,
    ConversationEventEnvelopeDto,
    ConversationSnapshotDto,
    ControllerResultDto,
    DashboardDto,
    ExecutionStepDto,
    FindingDto,
    FindingExplanationDto,
    GeneratedReportDto,
    ReportDto,
    SessionEventDto,
    SessionHistoryDto,
    SessionSummaryDto,
)


def to_payload(dto: object | None) -> dict[str, Any]:
    if dto is None:
        return {}
    return asdict(dto)


def serialize_clarification_request(
    request: ClarificationRequest | None,
) -> ClarificationRequestDto | None:
    if request is None:
        return None
    return ClarificationRequestDto(
        request_id=request.request_id,
        kind=request.kind.value,
        question=request.question,
        missing_fields=list(request.missing_fields),
        original_request=request.original_request,
        context=dict(request.context),
    )


def serialize_conversation_snapshot(
    context: ConversationContext,
) -> ConversationSnapshotDto:
    return ConversationSnapshotDto(
        conversation_id=context.conversation_id,
        active_skill_name=context.active_skill_name,
        active_session_id=context.active_session_id,
        active_session_public_id=context.active_session_public_id,
        active_session_mode=(
            context.active_session_mode.value
            if context.active_session_mode is not None
            else None
        ),
        active_session_title=context.active_session_title,
        active_session_target_summary=context.active_session_target_summary,
        pending_clarification=serialize_clarification_request(context.pending_clarification),
    )


def serialize_session_summary(summary: SessionSummary) -> SessionSummaryDto:
    return SessionSummaryDto(
        id=summary.id,
        public_id=summary.public_id,
        title=summary.title,
        mode=summary.mode.value,
        status=summary.status.value,
        target_summary=summary.target_summary,
        reused=summary.reused,
    )


def serialize_history_summary(
    history: SessionHistorySummaryView,
    *,
    scope: str,
) -> SessionHistoryDto:
    counts = {
        "runs": history.layer_summary.runs,
        "logs": history.layer_summary.logs,
        "checkpoints": history.layer_summary.checkpoints,
        "jobs": history.layer_summary.jobs,
        "events": history.layer_summary.events,
        "memory_entries": history.layer_summary.memory_entries,
        "artifacts": history.layer_summary.artifacts,
        "findings": history.layer_summary.findings,
        "reports": history.layer_summary.reports,
    }
    return SessionHistoryDto(
        scope=scope,
        counts=counts,
        recent_runs=[item.public_id for item in history.recent_runs],
        recent_jobs=[item.public_id for item in history.recent_jobs],
        recent_artifacts=[item.public_id for item in history.recent_artifacts],
        recent_findings=[item.public_id for item in history.recent_findings],
        recent_reports=[item.public_id for item in history.recent_reports],
    )


def serialize_execution_step(step: ExecutionStepView) -> ExecutionStepDto:
    return ExecutionStepDto(
        source_type=step.source_type,
        occurred_at=step.occurred_at,
        title=step.title,
        detail=step.detail,
        status=step.status,
        level=step.level,
        run_public_id=step.run_public_id,
        job_public_id=step.job_public_id,
    )


def serialize_artifact(artifact: Artifact) -> ArtifactDto:
    return ArtifactDto(
        id=artifact.id,
        public_id=artifact.public_id,
        artifact_type=artifact.artifact_type,
        title=artifact.title,
        summary=artifact.summary,
        target_ref=artifact.target_ref,
        source_job_id=artifact.source_job_id,
        created_at=artifact.captured_at,
        artifact_path=artifact.artifact_path,
        content_type=artifact.content_type,
        hash_digest=artifact.hash_digest,
        metadata=dict(artifact.metadata),
    )


def serialize_finding(finding: Finding) -> FindingDto:
    return FindingDto(
        id=finding.id,
        public_id=finding.public_id,
        finding_type=finding.finding_type,
        title=finding.title,
        target_ref=finding.target_ref,
        severity=finding.severity,
        confidence=finding.confidence,
        status=finding.status.value,
        summary=finding.summary,
        source_job_id=finding.source_job_id,
        created_at=finding.created_at,
        impact=finding.impact,
        reproduction_notes=finding.reproduction_notes,
        next_action=finding.next_action,
    )


def serialize_session_event(event: SessionEvent) -> SessionEventDto:
    return SessionEventDto(
        id=event.id,
        event_type=event.event_type.value,
        level=event.level.value,
        message=event.message,
        target_ref=event.target_ref,
        tool_name=event.tool_name,
        created_at=event.created_at,
        job_id=event.job_id,
        tool_category=event.tool_category,
        reason_code=event.reason_code,
        payload=dict(event.payload),
    )


def serialize_finding_explanation(
    explanation: FindingExplanationTraceView,
) -> FindingExplanationDto:
    return FindingExplanationDto(
        finding=serialize_finding(explanation.finding),
        linked_artifacts=[serialize_artifact(item) for item in explanation.linked_artifacts],
        source_job_id=(
            explanation.source_job.public_id
            if explanation.source_job is not None
            else None
        ),
        supporting_job_ids=[item.public_id for item in explanation.supporting_jobs],
        related_events=[serialize_session_event(item) for item in explanation.related_events],
        related_run_ids=list(explanation.related_run_ids),
        missing_segments=list(explanation.missing_segments),
    )


def serialize_report(report: Report) -> ReportDto:
    return ReportDto(
        id=report.id,
        public_id=report.public_id,
        report_type=report.report_type,
        title=report.title,
        summary=report.summary,
        created_at=report.created_at,
        artifact_path=report.artifact_path,
        metadata=dict(report.metadata),
    )


def serialize_generated_report(
    payload: GeneratedReportPayload,
) -> GeneratedReportDto:
    return GeneratedReportDto(
        scope=payload.resolved_scope,
        report_type=payload.report_type.value,
        reused=payload.reused,
        report=serialize_report(payload.report) if payload.report is not None else None,
        linked_artifact_ids=list(payload.linked_artifact_ids),
        linked_finding_ids=list(payload.linked_finding_ids),
    )


def serialize_confirmation_request(
    request: ConfirmationRequest,
) -> ConfirmationRequestDto:
    return ConfirmationRequestDto(
        request_id=request.request_id,
        action_name=request.action_name,
        risk_level=request.risk_level,
        target_summary=request.target_summary,
        reason=request.reason,
        message=request.message,
    )


def serialize_confirmation_decision(
    decision: ConfirmationDecision,
) -> ConfirmationDecisionDto:
    return ConfirmationDecisionDto(
        request_id=decision.request_id,
        decision=decision.decision.value,
    )


def serialize_execution_progress_event(
    event: ExecutionProgressEvent,
) -> dict[str, Any]:
    return event.to_dict()


def serialize_record_lookup_payload(
    payload: RecordLookupPayload,
) -> dict[str, Any]:
    if payload.history_summary is not None:
        return {
            "kind": payload.query.kind.value,
            "scope": payload.resolved_scope,
            "history": to_payload(
                serialize_history_summary(
                    payload.history_summary,
                    scope=payload.resolved_scope,
                )
            ),
        }
    if payload.execution_steps:
        return {
            "kind": payload.query.kind.value,
            "scope": payload.resolved_scope,
            "steps": [to_payload(serialize_execution_step(item)) for item in payload.execution_steps],
        }
    if payload.artifacts:
        return {
            "kind": payload.query.kind.value,
            "scope": payload.resolved_scope,
            "artifacts": [to_payload(serialize_artifact(item)) for item in payload.artifacts],
        }
    if payload.findings:
        return {
            "kind": payload.query.kind.value,
            "scope": payload.resolved_scope,
            "findings": [to_payload(serialize_finding(item)) for item in payload.findings],
        }
    if payload.reports:
        return {
            "kind": payload.query.kind.value,
            "scope": payload.resolved_scope,
            "reports": [to_payload(serialize_report(item)) for item in payload.reports],
        }
    return {
        "kind": payload.query.kind.value,
        "scope": payload.resolved_scope,
        "lookup_identifier": payload.query.lookup_identifier,
    }


def serialize_controller_result(result: ControllerResult) -> ControllerResultDto:
    return ControllerResultDto(
        status=result.status.value,
        intent=result.intent.value,
        message=result.message,
        bind_session=result.bind_session,
        session_summary=(
            serialize_session_summary(result.session_summary)
            if result.session_summary is not None
            else None
        ),
        clarification_request=serialize_clarification_request(result.clarification_request),
        record_lookup=(
            serialize_record_lookup_payload(result.record_lookup_payload)
            if result.record_lookup_payload is not None
            else None
        ),
        finding_explanation=(
            serialize_finding_explanation(result.finding_explanation_payload.explanation)
            if result.finding_explanation_payload is not None
            and result.finding_explanation_payload.explanation is not None
            else None
        ),
        generated_report=(
            serialize_generated_report(result.generated_report_payload)
            if result.generated_report_payload is not None
            else None
        ),
    )


def serialize_dashboard(dashboard: SessionDashboard) -> DashboardDto:
    session_summary = SessionSummary(
        id=dashboard.session.id,
        public_id=dashboard.session.public_id,
        title=dashboard.session.title,
        mode=dashboard.session.mode,
        status=dashboard.session.status,
        target_summary=dashboard.session.target_summary,
        reused=True,
    )
    policy = {
        "allowed_hosts": list(dashboard.policy.allowed_hosts),
        "allowed_domains": list(dashboard.policy.allowed_domains),
        "allowed_cidrs": list(dashboard.policy.allowed_cidrs),
        "allowed_ports": list(dashboard.policy.allowed_ports),
        "allowed_protocols": list(dashboard.policy.allowed_protocols),
        "denied_targets": list(dashboard.policy.denied_targets),
        "allowed_tool_categories": list(dashboard.policy.allowed_tool_categories),
        "max_concurrency": dashboard.policy.max_concurrency,
        "rate_limit_per_minute": dashboard.policy.rate_limit_per_minute,
        "confirmation_required_actions": list(dashboard.policy.confirmation_required_actions),
    }
    return DashboardDto(
        session=serialize_session_summary(session_summary),
        policy=policy,
        job_counts=dict(dashboard.job_counts),
        flagged_job_ids=[item.public_id for item in dashboard.flagged_jobs],
        finding_counts=dict(dashboard.finding_counts),
        recent_findings=[serialize_finding(item) for item in dashboard.recent_findings],
        artifact_count=dashboard.artifact_count,
        recent_artifacts=[serialize_artifact(item) for item in dashboard.recent_artifacts],
        report_count=dashboard.report_count,
        event_counts=dict(dashboard.event_counts),
        recent_events=[serialize_session_event(item) for item in dashboard.recent_events],
    )


def serialize_envelope(
    *,
    conversation_id: str,
    sequence: int,
    event_kind: str,
    timestamp: str,
    payload: dict[str, Any],
    session_id: str | None,
    session_public_id: str | None,
) -> ConversationEventEnvelopeDto:
    return ConversationEventEnvelopeDto(
        conversation_id=conversation_id,
        sequence=sequence,
        event_kind=event_kind,
        session_id=session_id,
        session_public_id=session_public_id,
        timestamp=timestamp,
        payload=payload,
    )
