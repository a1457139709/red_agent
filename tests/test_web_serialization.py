from agent.settings import Settings
from app.session_service import SessionService
from controller.contracts import ClarificationKind, ClarificationRequest, ControllerIntent, ControllerResult
from models.conversation_context import ConversationContext
from models.session import SessionMode, SessionStatus
from web.serialization import serialize_controller_result, serialize_conversation_snapshot


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_web_serialization_converts_conversation_context(tmp_path):
    _settings = build_settings(tmp_path)
    context = ConversationContext(
        conversation_id="conv-1",
        active_skill_name="security-audit",
        requested_session_mode=SessionMode.REDTEAM,
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_title="Session",
        active_session_target_summary="example.com",
        pending_clarification=ClarificationRequest(
            kind=ClarificationKind.RECORD_SCOPE,
            question="Which session should I use?",
            missing_fields=["session_scope"],
            original_request="what did you already do",
        ),
    )

    dto = serialize_conversation_snapshot(context)

    assert dto.conversation_id == "conv-1"
    assert dto.requested_session_mode == "redteam"
    assert dto.pending_clarification is not None
    assert dto.pending_clarification.kind == "record_scope"


def test_web_serialization_converts_controller_result(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Session",
        goal="Goal",
        mode=SessionMode.NORMAL,
        status=SessionStatus.ACTIVE,
    )
    result = ControllerResult.handled(
        intent=ControllerIntent.NORMAL_REQUEST,
        message="ok",
        session_summary=type("SummaryLike", (), {
            "id": session.id,
            "public_id": session.public_id,
            "title": session.title,
            "mode": session.mode,
            "status": session.status,
            "target_summary": session.target_summary,
            "reused": False,
        })(),
        bind_session=True,
    )

    dto = serialize_controller_result(result)

    assert dto.status == "handled"
    assert dto.session_summary is not None
    assert dto.session_summary.public_id == session.public_id
