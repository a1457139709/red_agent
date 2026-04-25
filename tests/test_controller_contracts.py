from controller.contracts import (
    ClarificationKind,
    ClarificationRequest,
    ConfirmationDecision,
    ConfirmationDecisionValue,
    ConfirmationRequest,
    ControllerIntent,
    ControllerRequest,
    ControllerResult,
    ControllerResultStatus,
    ExecutionBridge,
    ExecutionBridgeKind,
    GeneratedReportPayload,
    RecordLookupKind,
    RecordLookupPayload,
    RecordQueryRequest,
    ReportType,
    SessionSummary,
)
from models.session import Session, SessionMode, SessionPersistenceMode, SessionStatus
from models.report import Report


def test_controller_request_detects_slash_commands():
    assert ControllerRequest(raw_input="/help").is_slash_command
    assert not ControllerRequest(raw_input="summarize this repo").is_slash_command


def test_controller_result_helpers_build_structured_payloads():
    session = Session.create(
        title="Normal Session",
        goal="Summarize the repo",
        mode=SessionMode.NORMAL,
        persistence_mode=SessionPersistenceMode.EPHEMERAL,
        workspace="D:/workspace",
        status=SessionStatus.ACTIVE,
    )
    session.public_id = "S0001"
    summary = SessionSummary.from_session(session, reused=False)
    clarification = ClarificationRequest(
        kind=ClarificationKind.RECORD_SCOPE,
        question="Which session should I use?",
        missing_fields=["session_scope"],
        original_request="what did you already do",
    )

    handled = ControllerResult.handled(
        intent=ControllerIntent.NORMAL_REQUEST,
        session_summary=summary,
        record_lookup_payload=RecordLookupPayload(
            session_summary=summary,
            query=RecordQueryRequest(kind=RecordLookupKind.SESSION_HISTORY),
            resolved_scope="current",
        ),
        execution_bridge=ExecutionBridge(
            kind=ExecutionBridgeKind.BASE_RUNTIME,
            prompt_text="summarize this repo",
        ),
        bind_session=True,
    )
    needs_clarification = ControllerResult.clarification_required(
        message=clarification.question,
        clarification_request=clarification,
    )
    delegated = ControllerResult.delegated_to_advanced_command()
    unsupported = ControllerResult.unsupported(message="Unsupported")

    assert handled.status == ControllerResultStatus.HANDLED
    assert handled.execution_bridge is not None
    assert handled.bind_session
    assert handled.session_summary is not None
    assert handled.record_lookup_payload is not None
    assert needs_clarification.status == ControllerResultStatus.CLARIFICATION_REQUIRED
    assert needs_clarification.clarification_request is not None
    assert delegated.status == ControllerResultStatus.DELEGATED_TO_ADVANCED_COMMAND
    assert unsupported.status == ControllerResultStatus.UNSUPPORTED


def test_record_query_request_and_report_payload_normalize_values():
    session = Session.create(
        title="Report Session",
        goal="Summarize the session",
        mode=SessionMode.NORMAL,
        persistence_mode=SessionPersistenceMode.EPHEMERAL,
        workspace="D:/workspace",
        status=SessionStatus.ACTIVE,
    )
    session.public_id = "S0002"
    summary = SessionSummary.from_session(session, reused=True)
    query = RecordQueryRequest(
        kind="reports",
        explicit_scope="S0002",
        report_type="operator_report",
        source_command="/REPORT",
    )
    payload = GeneratedReportPayload(
        session_summary=summary,
        query=query,
        resolved_scope="S0002",
        report_type=query.report_type,
        report=Report.create(
            session_id=session.id,
            report_type="operator_report",
            title="Operator report",
            summary="Readable report",
        ),
        reused=True,
        linked_artifact_ids=["A0001"],
        linked_finding_ids=["F0001"],
    )

    assert query.kind == RecordLookupKind.REPORTS
    assert query.report_type == ReportType.OPERATOR_REPORT
    assert query.source_command == "/report"
    assert query.requests_report_generation
    assert payload.report_type == ReportType.OPERATOR_REPORT
    assert payload.report is not None
    assert payload.reused
    assert payload.linked_artifact_ids == ["A0001"]
    assert payload.linked_finding_ids == ["F0001"]


def test_confirmation_contracts_are_structured():
    request = ConfirmationRequest(
        action_name="poc_execute",
        risk_level="dangerous",
        target_summary="example.com",
        reason="dangerous action",
        message="Requires approval",
    )
    decision = ConfirmationDecision(
        request_id=request.request_id,
        decision=ConfirmationDecisionValue.APPROVE,
    )

    assert request.action_name == "poc_execute"
    assert decision.request_id == request.request_id
    assert decision.decision == ConfirmationDecisionValue.APPROVE
