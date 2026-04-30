from web.contracts import (
    ConversationSnapshotDto,
    ControllerResultDto,
    MissingFieldErrorDto,
    SessionSummaryDto,
    WebEventKind,
)


def test_web_event_kind_values_are_stable():
    assert WebEventKind.CONTROLLER_RESULT.value == "controller_result"
    assert WebEventKind.CONFIRMATION_REQUIRED.value == "confirmation_required"
    assert WebEventKind.FINAL_ANSWER.value == "final_answer"
    assert "clarification_required" not in {item.value for item in WebEventKind}


def test_web_contract_dtos_hold_serializable_fields():
    summary = SessionSummaryDto(
        id="session-1",
        public_id="S0001",
        title="Session",
        mode="normal",
        status="active",
        target_summary="example.com",
        reused=False,
    )
    snapshot = ConversationSnapshotDto(
        conversation_id="conv-1",
        active_skill_name="security-audit",
        requested_session_mode="normal",
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode="normal",
        active_session_title="Session",
        active_session_target_summary="example.com",
    )
    result = ControllerResultDto(
        status="missing_fields",
        intent="record_lookup_request",
        message="No active session. Use /status latest or /status S0001.",
        bind_session=False,
        missing_field_error=MissingFieldErrorDto(
            message="No active session. Use /status latest or /status S0001.",
            missing_fields=["session_scope"],
            allowed_values={"session_scope": ["current", "latest", "S0001"]},
        ),
    )

    assert snapshot.conversation_id == "conv-1"
    assert result.missing_field_error is not None
    assert result.missing_field_error.missing_fields == ["session_scope"]
