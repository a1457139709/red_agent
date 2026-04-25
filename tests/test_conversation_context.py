from controller.contracts import ClarificationRequest, ClarificationKind, SessionSummary
from models.conversation_context import ConversationContext
from models.session import SessionMode, SessionStatus


def test_conversation_context_binds_and_clears_session_state():
    context = ConversationContext(active_skill_name="security-audit")
    summary = SessionSummary(
        id="session-1",
        public_id="S0001",
        title="Session",
        mode=SessionMode.NORMAL,
        status=SessionStatus.ACTIVE,
        target_summary="example.com",
        reused=False,
    )

    context.bind_session(summary)

    assert context.active_session_label() == "S0001"
    assert context.active_session_title == "Session"
    assert context.active_session_target_summary == "example.com"

    context.clear_active_session()

    assert context.active_session_id is None
    assert context.active_session_public_id is None
    assert context.active_session_mode is None
    assert context.requested_session_mode == SessionMode.NORMAL
    assert context.active_skill_name == "security-audit"


def test_conversation_context_clears_pending_clarification_only():
    clarification = ClarificationRequest(
        kind=ClarificationKind.RECORD_SCOPE,
        question="Which session should I use?",
        missing_fields=["session_scope"],
        original_request="what did you already do",
    )
    context = ConversationContext(pending_clarification=clarification)

    context.clear_pending_clarification()

    assert context.pending_clarification is None


def test_conversation_context_tracks_requested_session_mode():
    context = ConversationContext()

    context.set_requested_session_mode(SessionMode.REDTEAM)

    assert context.requested_session_mode == SessionMode.REDTEAM
