from web.contracts import (
    ConversationSnapshotDto,
    ControllerResultDto,
    SessionSummaryDto,
    WebEventKind,
)


def test_web_event_kind_values_are_stable():
    assert WebEventKind.CONTROLLER_RESULT.value == "controller_result"
    assert WebEventKind.CONFIRMATION_REQUIRED.value == "confirmation_required"
    assert WebEventKind.FINAL_ANSWER.value == "final_answer"


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
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode="normal",
        active_session_title="Session",
        active_session_target_summary="example.com",
    )
    result = ControllerResultDto(
        status="handled",
        intent="normal_request",
        message="ok",
        bind_session=True,
        session_summary=summary,
    )

    assert snapshot.conversation_id == "conv-1"
    assert result.session_summary is not None
    assert result.session_summary.public_id == "S0001"
