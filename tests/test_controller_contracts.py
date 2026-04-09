from controller.contracts import (
    ClarificationKind,
    ClarificationRequest,
    ControllerIntent,
    ControllerRequest,
    ControllerResult,
    ControllerResultStatus,
    ExecutionBridge,
    ExecutionBridgeKind,
    SessionSummary,
)
from models.session import Session, SessionMode, SessionPersistenceMode, SessionStatus


def test_controller_request_detects_slash_commands():
    assert ControllerRequest(raw_input="/task list").is_slash_command
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
        kind=ClarificationKind.BARE_TARGET,
        question="One-off or persistent?",
        missing_fields=["mode"],
        original_request="look at example.com",
    )

    handled = ControllerResult.handled(
        intent=ControllerIntent.NORMAL_REQUEST,
        session_summary=summary,
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
    assert needs_clarification.status == ControllerResultStatus.CLARIFICATION_REQUIRED
    assert needs_clarification.clarification_request is not None
    assert delegated.status == ControllerResultStatus.DELEGATED_TO_ADVANCED_COMMAND
    assert unsupported.status == ControllerResultStatus.UNSUPPORTED
