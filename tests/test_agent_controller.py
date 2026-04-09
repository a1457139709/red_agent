import asyncio

import main as main_module
from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.session_service import SessionService
from app.task_service import TaskService
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
from runtime.task_runner import TaskRunner
from tools import build_tool_registry
from tools.executor import ToolExecutor


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


def test_agent_controller_starts_redteam_session_without_execution_bridge(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    result = controller.handle(
        ControllerRequest(raw_input="Start a recon session for example.com")
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.REDTEAM_REQUEST
    assert result.execution_bridge is None
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
    assert redteam_result.execution_bridge is None
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
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    task_runner = TaskRunner(task_service, run_service, skill_service)
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"prompts": [], "answers": []}
    responses = iter(["inspect the configs", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        captured["prompts"].append((question, system_prompt, [tool.name for tool in tools or []]))
        return {
            "status": "completed",
            "response": "done",
            "messages": [],
            "usage": {"total_tokens": 8},
        }

    monkeypatch.setattr(main_module, "agent_loop", fake_agent_loop)
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
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    question, system_prompt, _tool_names = captured["prompts"][0]
    assert question == "inspect the configs"
    assert "Security Audit" in system_prompt
    assert shell_state.active_session_mode is not None
    assert shell_state.active_session_mode.value == "normal"
    assert shell_state.active_session_public_id is not None
    assert build_prompt(shell_state) == "\nskill:security-audit > "


def test_run_interactive_shell_keeps_plain_text_on_session_flow_with_active_task_binding(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState(active_task_id="task-1", active_task_public_id="T0001")
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    task_runner = TaskRunner(task_service, run_service, skill_service)
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"prompts": [], "answers": []}
    responses = iter(["inspect the configs", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        captured["prompts"].append((question, system_prompt))
        return {
            "status": "completed",
            "response": "done",
            "messages": [],
            "usage": {"total_tokens": 8},
        }

    monkeypatch.setattr(main_module, "agent_loop", fake_agent_loop)
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
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert len(captured["prompts"]) == 1
    assert captured["prompts"][0][0] == "inspect the configs"
    assert shell_state.active_task_id == "task-1"
    assert shell_state.active_task_public_id == "T0001"
    assert shell_state.active_session_mode == SessionMode.NORMAL
    assert shell_state.active_session_public_id is not None
    assert build_prompt(shell_state).startswith("\nnormal:")


def test_run_interactive_shell_redteam_startup_binds_session_without_agent_execution(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    skill_service = main_module.create_skill_service()
    task_runner = TaskRunner(task_service, run_service, skill_service)
    tool_executor = ToolExecutor(build_tool_registry())
    responses = iter(["Start a recon session for example.com", "/quit"])

    def fake_input(_prompt):
        return next(responses)

    async def fail_agent_loop(*args, **kwargs):
        raise AssertionError("agent_loop should not run for Phase 2 redteam startup")

    monkeypatch.setattr(main_module, "agent_loop", fail_agent_loop)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert shell_state.active_session_mode is not None
    assert shell_state.active_session_mode.value == "redteam"
    assert build_prompt(shell_state).startswith("\nredteam:")


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


def test_build_prompt_prefers_session_over_legacy_task_binding():
    shell_state = ShellState(
        active_task_id="task-1",
        active_task_public_id="T0001",
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode=SessionMode.NORMAL,
    )

    assert build_prompt(shell_state) == "\nnormal:S0001 > "
