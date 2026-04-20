import asyncio

import main as main_module
from runtime.execution_events import ExecutionOutcome
from agent.settings import Settings
from agent.state import SessionState
from app.session_service import SessionService
from controller.agent_controller import AgentController
from controller.contracts import (
    ClarificationKind,
    ControllerIntent,
    ControllerRequest,
    ControllerResult,
    ControllerResultStatus,
    ExecutionBridgeKind,
)
from main import (
    ShellState,
    build_controller_request,
    build_prompt,
    handle_clear_command,
    render_controller_result,
    run_interactive_shell,
)
from models.session import SessionMode
from tools import build_tool_registry
from tools.executor import ToolExecutor


class FakeExecutionService:
    def __init__(self, *, outcome: ExecutionOutcome | None = None) -> None:
        self.calls: list[dict[str, str | None]] = []
        self.outcome = outcome or ExecutionOutcome(status="completed", response="done")

    async def execute_session(
        self,
        *,
        session_identifier: str,
        prompt_text: str,
        session_state,
        skill_service,
        tool_executor,
        settings,
        skill_name: str | None = None,
        on_progress=None,
        on_info=None,
        on_error=None,
        on_confirmation=None,
    ) -> ExecutionOutcome:
        self.calls.append(
            {
                "session_identifier": session_identifier,
                "prompt_text": prompt_text,
                "skill_name": skill_name,
            }
        )
        return self.outcome


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_agent_controller_creates_and_reuses_normal_session(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    first = controller.handle(ControllerRequest(raw_input="Summarize this repository"))
    second = controller.handle(
        ControllerRequest(
            raw_input="Summarize the tests too",
            active_session_id=first.session_summary.id if first.session_summary else None,
            active_session_public_id=first.session_summary.public_id if first.session_summary else None,
            active_session_mode=first.session_summary.mode if first.session_summary else None,
        )
    )

    assert first.status == ControllerResultStatus.HANDLED
    assert first.intent == ControllerIntent.NORMAL_REQUEST
    assert first.execution_bridge is not None
    assert first.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert first.session_summary is not None
    assert second.session_summary is not None
    assert second.session_summary.public_id == first.session_summary.public_id
    assert second.session_summary.reused


def test_agent_controller_starts_redteam_session_with_execution_bridge(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    result = controller.handle(
        ControllerRequest(raw_input="Start a recon session for example.com")
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.REDTEAM_REQUEST
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.session_summary is not None
    assert result.session_summary.mode.value == "redteam"
    assert result.bind_session


def test_agent_controller_requires_clarification_for_bare_target_and_resolves_answer(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    first = controller.handle(ControllerRequest(raw_input="look at example.com"))
    resolved = controller.handle(
        ControllerRequest(
            raw_input="one-off check",
            pending_clarification=first.clarification_request,
        )
    )

    assert first.status == ControllerResultStatus.CLARIFICATION_REQUIRED
    assert first.clarification_request is not None
    assert first.clarification_request.kind == ClarificationKind.BARE_TARGET
    assert resolved.status == ControllerResultStatus.HANDLED
    assert resolved.execution_bridge is not None
    assert resolved.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME


def test_agent_controller_record_lookup_prefers_active_session(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    session = session_service.create_session(
        title="Current",
        goal="Track current work",
        mode="normal",
        status="active",
    )

    result = controller.handle(
        ControllerRequest(
            raw_input="What did you already do?",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.RECORD_LOOKUP_REQUEST
    assert result.session_summary is not None
    assert result.session_summary.public_id == session.public_id
    assert not result.bind_session


def test_agent_controller_active_task_does_not_override_normal_session_routing(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    result = controller.handle(
        ControllerRequest(
            raw_input="Summarize the deployment scripts",
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.session_summary is not None
    assert result.intent == ControllerIntent.NORMAL_REQUEST


def test_agent_controller_active_task_does_not_override_record_lookup_or_redteam_startup(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    session = session_service.create_session(
        title="Current",
        goal="Track current work",
        mode="normal",
        status="active",
    )

    record_result = controller.handle(
        ControllerRequest(
            raw_input="What did you already do?",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )
    redteam_result = controller.handle(
        ControllerRequest(
            raw_input="Start a recon session for example.com",
        )
    )
    clarification_result = controller.handle(
        ControllerRequest(
            raw_input="scan this host",
        )
    )

    assert record_result.intent == ControllerIntent.RECORD_LOOKUP_REQUEST
    assert record_result.execution_bridge is None
    assert redteam_result.intent == ControllerIntent.REDTEAM_REQUEST
    assert redteam_result.execution_bridge is not None
    assert redteam_result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert clarification_result.status == ControllerResultStatus.CLARIFICATION_REQUIRED
    assert clarification_result.execution_bridge is None


def test_agent_controller_clarification_preserves_all_resolved_targets_in_execution_prompt(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    first = controller.handle(ControllerRequest(raw_input="scan this host"))
    resolved = controller.handle(
        ControllerRequest(
            raw_input="Use example.com and 10.0.0.1 for a one-off check",
            pending_clarification=first.clarification_request,
        )
    )

    assert first.status == ControllerResultStatus.CLARIFICATION_REQUIRED
    assert resolved.status == ControllerResultStatus.HANDLED
    assert resolved.execution_bridge is not None
    assert resolved.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert resolved.execution_bridge.prompt_text.startswith("scan this host\nTargets:\n")
    assert "- domain: example.com" in resolved.execution_bridge.prompt_text
    assert "- ip: 10.0.0.1" in resolved.execution_bridge.prompt_text
    assert resolved.session_summary is not None
    assert resolved.session_summary.target_summary is not None
    assert "example.com" in resolved.session_summary.target_summary
    assert "10.0.0.1" in resolved.session_summary.target_summary


def test_render_controller_result_uses_callback_presenter(tmp_path):
    outputs = []
    session_service = SessionService.from_settings(build_settings(tmp_path))
    controller = AgentController.from_session_service(session_service)
    result = controller.handle(ControllerRequest(raw_input="Start a recon session for example.com"))
    presenter = main_module.CliPresenter.for_callbacks(info_output=outputs.append, error_output=outputs.append)

    render_controller_result(result, ui=presenter)

    assert any("Started session" in message or "Started redteam session" in message for message in outputs)
    assert any("Mode: redteam" in message for message in outputs)


def test_run_interactive_shell_routes_plain_text_through_controller_and_skill_bridge(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState(active_skill_name="security-audit")
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"answers": []}
    responses = iter(["inspect the configs", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    monkeypatch.setattr(main_module.ColoredOutput, "print_final_answer", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_error", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_info", captured["answers"].append)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            execution_service=execution_service,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert len(execution_service.calls) == 1
    assert execution_service.calls[0]["prompt_text"] == "inspect the configs"
    assert execution_service.calls[0]["skill_name"] == "security-audit"
    assert shell_state.active_session_mode is not None
    assert shell_state.active_session_mode.value == "normal"
    assert shell_state.active_session_public_id is not None
    assert build_prompt(shell_state) == "\nskill:security-audit > "
    assert "done" in captured["answers"]


def test_run_interactive_shell_keeps_plain_text_on_session_flow_with_active_session_binding(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState(
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode=SessionMode.NORMAL,
    )
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"answers": []}
    responses = iter(["inspect the configs", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    monkeypatch.setattr(main_module.ColoredOutput, "print_final_answer", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_error", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_info", captured["answers"].append)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            execution_service=execution_service,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert len(execution_service.calls) == 1
    assert execution_service.calls[0]["prompt_text"] == "inspect the configs"
    assert shell_state.active_session_mode == SessionMode.NORMAL
    assert shell_state.active_session_public_id is not None
    assert build_prompt(shell_state).startswith("\nnormal:")
    assert "done" in captured["answers"]


def test_run_interactive_shell_redteam_startup_executes_in_foreground(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    responses = iter(["Start a recon session for example.com", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            execution_service=execution_service,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert shell_state.active_session_mode is not None
    assert shell_state.active_session_mode.value == "redteam"
    assert build_prompt(shell_state).startswith("\nredteam:")
    assert len(execution_service.calls) == 1
    assert execution_service.calls[0]["prompt_text"] == "Start a recon session for example.com"


def test_build_controller_request_and_clear_command_preserve_session_binding(tmp_path):
    session_state = SessionState()
    session_state.append_user_message("hello")
    shell_state = ShellState(
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode=SessionMode.NORMAL,
        active_session_title="Session",
        active_session_target_summary="example.com",
        active_skill_name="security-audit",
        pending_clarification=ControllerResult.clarification_required(
            message="clarify",
            clarification_request=main_module.ClarificationRequest(
                kind="bare_target",
                question="One-off or persistent?",
                missing_fields=["mode"],
                original_request="look at example.com",
            ),
        ).clarification_request,
    )

    request = build_controller_request(question="inspect configs", shell_state=shell_state)
    assert request.active_session_public_id == "S0001"
    assert request.pending_clarification is not None

    handle_clear_command("/clear", shell_state=shell_state, session_state=session_state)

    assert shell_state.active_session_public_id == "S0001"
    assert shell_state.active_session_mode == SessionMode.NORMAL
    assert shell_state.pending_clarification is None
    assert shell_state.active_skill_name == "security-audit"


def test_build_prompt_prefers_session_binding():
    shell_state = ShellState(
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode=SessionMode.NORMAL,
    )

    assert build_prompt(shell_state) == "\nnormal:S0001 > "


def test_run_interactive_shell_rejects_removed_operation_job_and_evidence_commands(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    errors: list[str] = []
    responses = iter(["/operation list", "/job list S0001", "/evidence list S0001", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    monkeypatch.setattr(
        main_module,
        "get_presenter",
        lambda: main_module.CliPresenter.for_callbacks(error_output=errors.append),
    )
    monkeypatch.setattr(main_module.ColoredOutput, "print_header", lambda *_args, **_kwargs: None)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            execution_service=execution_service,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert execution_service.calls == []
    assert any("Unknown command: /operation list" in message for message in errors)
    assert any("Unknown command: /job list S0001" in message for message in errors)
    assert any("Unknown command: /evidence list S0001" in message for message in errors)
