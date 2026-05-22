import asyncio

import main as main_module
from runtime.execution_events import ExecutionOutcome
from agent.settings import Settings
from agent.state import SessionState
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.report_service import ReportService
from app.run_service import RunService
from app.session_service import SessionService
from app.session_event_service import SessionEventService
from controller.agent_controller import AgentController
from controller.contracts import (
    ConfirmationDecisionValue,
    ConfirmationRequest,
    ControllerIntent,
    ControllerRequest,
    ControllerResult,
    ControllerResultStatus,
    ExecutionBridgeKind,
    RecordLookupKind,
    ReportType,
    SessionSummary,
)
from main import (
    ShellState,
    build_controller_request,
    build_prompt,
    handle_clear_command,
    handle_normal_command,
    prompt_execution_confirmation,
    handle_redteam_command,
    render_controller_result,
    run_interactive_shell,
)
from models.job import JobStatus
from models.run import SessionLogLevel
from models.session import SessionMode
from models.session_event import SessionEventLevel, SessionEventType
from tools import build_tool_registry
from tools.executor import ToolExecutor


class FakeExecutionService:
    def __init__(self, *, outcome: ExecutionOutcome | None = None) -> None:
        self.calls: list[dict[str, str | None]] = []
        self.module_calls: list[dict[str, object]] = []
        self.outcome = outcome or ExecutionOutcome(status="completed", response="done")

    async def execute_session(
        self,
        *,
        session_identifier: str,
        prompt_text: str,
        session_state,
        capability_service,
        tool_executor,
        settings,
        conversation_context=None,
        interaction_port=None,
        skill_name: str | None = None,
        on_info=None,
        on_error=None,
    ) -> ExecutionOutcome:
        self.calls.append(
            {
                "session_identifier": session_identifier,
                "prompt_text": prompt_text,
                "skill_name": skill_name,
            }
        )
        return self.outcome

    async def execute_module(
        self,
        *,
        invocation,
        tool_executor,
        conversation_context=None,
        interaction_port=None,
    ) -> ExecutionOutcome:
        self.module_calls.append(
            {
                "module_name": invocation.module.manifest.name,
                "parameters": dict(invocation.parameters),
                "one_shot": invocation.one_shot,
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


def seed_record_lookup_session(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    report_service = ReportService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    session = session_service.create_session(
        title="Lookup Session",
        goal="Return query records",
        mode="redteam",
        status="active",
    )
    run = run_service.start_run(session.public_id)
    run_service.write_log(
        session_identifier=session.public_id,
        run_id=run.id,
        level=SessionLogLevel.INFO,
        message="tool_completed",
        payload={"tool_name": "http_probe"},
    )
    run = run_service.complete_run(run.id, step_count=1)
    job = job_service.create_job(
        session_identifier=session.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        status=JobStatus.SUCCEEDED,
    )
    event_service.create_event(
        session_identifier=session.public_id,
        job_identifier=job.public_id,
        event_type=SessionEventType.EXECUTION_SUCCEEDED,
        level=SessionEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Probe completed.",
        payload={"run_id": run.public_id},
    )
    artifact = artifact_service.create_artifact(
        session_identifier=session.public_id,
        source_job_identifier=job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response.",
    )
    finding = finding_service.create_finding(
        session_identifier=session.public_id,
        source_job_identifier=job.public_id,
        finding_type="reachable_service",
        title="Reachable service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Responded successfully.",
    )
    finding_service.link_artifacts(finding.public_id, [artifact.public_id])
    report = report_service.create_report(
        session_identifier=session.public_id,
        report_type="session_summary",
        title="Session summary",
        summary="Summarize the session.",
        artifact_identifiers=[artifact.public_id],
        finding_identifiers=[finding.public_id],
        output_payload={"ok": True},
    )

    return settings, controller, session, artifact, finding, report


def test_agent_controller_requires_active_session_for_free_form_prompt(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    result = controller.handle(ControllerRequest(raw_input="Summarize this repository"))

    assert result.status == ControllerResultStatus.UNSUPPORTED
    assert result.execution_bridge is None
    assert "No active session is bound" in (result.message or "")


def test_agent_controller_reuses_bound_normal_session_for_free_form_prompt(tmp_path):
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
            raw_input="Summarize the tests too",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.NORMAL_REQUEST
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.execution_bridge.prompt_text == "Summarize the tests too"
    assert result.session_summary is not None
    assert result.session_summary.public_id == session.public_id
    assert result.session_summary.reused


def test_agent_controller_uses_bound_redteam_session_for_free_form_prompt(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    session = session_service.create_session(
        title="Redteam current",
        goal="Track redteam work",
        mode="redteam",
        status="active",
    )

    result = controller.handle(
        ControllerRequest(
            raw_input="Scan example.com for open services",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.REDTEAM_REQUEST
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.session_summary is not None
    assert result.session_summary.mode.value == "redteam"
    assert result.session_summary.public_id == session.public_id
    assert result.bind_session


def test_agent_controller_keeps_free_form_target_text_unparsed(tmp_path):
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
            raw_input="look at example.com",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.NORMAL_REQUEST
    assert result.missing_field_error is None
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.execution_bridge.prompt_text == "look at example.com"


def test_agent_controller_does_not_route_plain_text_as_module_request(tmp_path):
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
            raw_input="Run surface-recon for example.com",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.NORMAL_REQUEST
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.execution_bridge.module_name is None
    assert result.execution_bridge.prompt_text == "Run surface-recon for example.com"


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
        build_controller_request(
            question="/history",
            shell_state=ShellState(
                active_session_id=session.id,
                active_session_public_id=session.public_id,
                active_session_mode=session.mode,
            ),
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.RECORD_LOOKUP_REQUEST
    assert result.session_summary is not None
    assert result.session_summary.public_id == session.public_id
    assert result.record_lookup_payload is not None
    assert result.record_lookup_payload.query.kind == RecordLookupKind.SESSION_HISTORY
    assert not result.bind_session


def test_agent_controller_handles_structured_history_command_with_active_session(tmp_path):
    _settings, controller, session, _artifact, _finding, _report = seed_record_lookup_session(tmp_path)

    result = controller.handle(
        build_controller_request(
            question="/history",
            shell_state=ShellState(
                active_session_id=session.id,
                active_session_public_id=session.public_id,
                active_session_mode=session.mode,
            ),
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.intent == ControllerIntent.RECORD_LOOKUP_REQUEST
    assert result.record_lookup_payload is not None
    assert result.record_lookup_payload.query.kind == RecordLookupKind.SESSION_HISTORY
    assert result.record_lookup_payload.resolved_scope == session.public_id
    assert result.record_lookup_payload.history_summary is not None
    assert result.record_lookup_payload.history_summary.layer_summary.artifacts == 1
    assert result.session_summary is not None
    assert result.session_summary.public_id == session.public_id


def test_agent_controller_structured_history_command_requires_scope_without_active_session(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    result = controller.handle(
        build_controller_request(
            question="/history",
            shell_state=ShellState(),
        )
    )

    assert result.status == ControllerResultStatus.MISSING_FIELDS
    assert result.missing_field_error is not None
    assert result.missing_field_error.missing_fields == ["session_scope"]
    assert result.missing_field_error.allowed_values == {
        "session_scope": ["current", "latest", "S0001"],
    }
    assert result.message == "No active session. Use /history latest or /history S0001."


def test_agent_controller_handles_structured_report_command_with_explicit_scope(tmp_path):
    _settings, controller, session, _artifact, _finding, _report = seed_record_lookup_session(tmp_path)

    result = controller.handle(
        build_controller_request(
            question=f"/reports generate operator_report {session.public_id}",
            shell_state=ShellState(),
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.generated_report_payload is not None
    assert result.generated_report_payload.report_type == ReportType.OPERATOR_REPORT
    assert result.generated_report_payload.resolved_scope == session.public_id
    assert result.generated_report_payload.report is not None
    assert result.generated_report_payload.report.report_type == ReportType.OPERATOR_REPORT.value
    assert not result.generated_report_payload.reused
    assert result.session_summary is not None
    assert result.session_summary.public_id == session.public_id


def test_agent_controller_reuses_existing_generated_report(tmp_path):
    _settings, controller, session, _artifact, _finding, _report = seed_record_lookup_session(tmp_path)

    first = controller.handle(
        build_controller_request(
            question=f"/reports generate operator_report {session.public_id}",
            shell_state=ShellState(),
        )
    )
    second = controller.handle(
        build_controller_request(
            question=f"/reports generate operator_report {session.public_id}",
            shell_state=ShellState(),
        )
    )

    assert first.generated_report_payload is not None
    assert second.generated_report_payload is not None
    assert not first.generated_report_payload.reused
    assert second.generated_report_payload.reused
    assert second.generated_report_payload.report is not None
    assert first.generated_report_payload.report is not None
    assert second.generated_report_payload.report.public_id == first.generated_report_payload.report.public_id


def test_agent_controller_returns_real_artifact_records_for_structured_lookup(tmp_path):
    _settings, controller, session, artifact, _finding, _report = seed_record_lookup_session(tmp_path)

    result = controller.handle(
        build_controller_request(
            question=f"/show {artifact.public_id} {session.public_id}",
            shell_state=ShellState(),
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.record_lookup_payload is not None
    assert [item.public_id for item in result.record_lookup_payload.artifacts] == [artifact.public_id]


def test_agent_controller_returns_traceable_finding_explanation(tmp_path):
    _settings, controller, session, artifact, finding, _report = seed_record_lookup_session(tmp_path)

    result = controller.handle(
        build_controller_request(
            question=f"/why {finding.public_id} {session.public_id}",
            shell_state=ShellState(),
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.finding_explanation_payload is not None
    assert result.finding_explanation_payload.explanation is not None
    explanation = result.finding_explanation_payload.explanation
    assert explanation.finding.public_id == finding.public_id
    assert [item.public_id for item in explanation.linked_artifacts] == [artifact.public_id]
    assert explanation.missing_segments == []


def test_agent_controller_free_form_prompt_without_session_is_not_auto_routed(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)

    result = controller.handle(
        ControllerRequest(
            raw_input="Summarize the deployment scripts",
        )
    )

    assert result.status == ControllerResultStatus.UNSUPPORTED
    assert result.execution_bridge is None


def test_agent_controller_active_session_does_not_reclassify_free_form_text(tmp_path):
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
        build_controller_request(
            question="/history",
            shell_state=ShellState(
                active_session_id=session.id,
                active_session_public_id=session.public_id,
                active_session_mode=session.mode,
            ),
        )
    )
    prompt_result = controller.handle(
        ControllerRequest(
            raw_input="Scan example.com for open services",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )
    normal_result = controller.handle(
        ControllerRequest(
            raw_input="scan this host",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert record_result.intent == ControllerIntent.RECORD_LOOKUP_REQUEST
    assert record_result.execution_bridge is None
    assert prompt_result.intent == ControllerIntent.NORMAL_REQUEST
    assert prompt_result.execution_bridge is not None
    assert prompt_result.execution_bridge.prompt_text == "Scan example.com for open services"
    assert normal_result.intent == ControllerIntent.NORMAL_REQUEST
    assert normal_result.execution_bridge is not None


def test_agent_controller_does_not_extract_targets_from_free_form_prompt(tmp_path):
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
            raw_input="Inspect example.com and 10.0.0.1 for exposed services",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )

    assert result.status == ControllerResultStatus.HANDLED
    assert result.execution_bridge is not None
    assert result.execution_bridge.kind == ExecutionBridgeKind.BASE_RUNTIME
    assert result.execution_bridge.prompt_text == "Inspect example.com and 10.0.0.1 for exposed services"
    assert result.session_summary is not None
    assert result.session_summary.target_summary is None


def test_render_controller_result_uses_callback_presenter(tmp_path):
    outputs = []
    session_service = SessionService.from_settings(build_settings(tmp_path))
    controller = AgentController.from_session_service(session_service)
    session = session_service.create_session(
        title="Redteam current",
        goal="Track redteam work",
        mode="redteam",
        status="active",
    )
    result = controller.handle(
        ControllerRequest(
            raw_input="Scan example.com for open services",
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=session.mode,
        )
    )
    presenter = main_module.CliPresenter.for_callbacks(info_output=outputs.append, error_output=outputs.append)

    render_controller_result(result, ui=presenter)

    assert any("Reused session" in message for message in outputs)
    assert any("Mode: redteam" in message for message in outputs)


def test_run_interactive_shell_routes_plain_text_through_controller_and_skill_bridge(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState(active_skill_name="security-audit")
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Current",
        goal="Track current work",
        mode="normal",
        status="active",
    )
    shell_state.bind_session(SessionSummary.from_session(session, reused=True))
    controller = AgentController.from_session_service(session_service)
    capability_service = main_module.create_capability_service()
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
            capability_service=capability_service,
            input_func=fake_input,
        )
    )

    assert len(execution_service.calls) == 1
    assert execution_service.calls[0]["prompt_text"] == "inspect the configs"
    assert execution_service.calls[0]["skill_name"] == "security-audit"
    assert shell_state.active_session_mode is not None
    assert shell_state.active_session_mode.value == "normal"
    assert shell_state.active_session_public_id is not None
    assert build_prompt(shell_state).startswith("\nskill:security-audit normal:")
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
    session_service.create_session(
        title="Current",
        goal="Track current work",
        mode="normal",
        status="active",
    )
    controller = AgentController.from_session_service(session_service)
    capability_service = main_module.create_capability_service()
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
            capability_service=capability_service,
            input_func=fake_input,
        )
    )

    assert len(execution_service.calls) == 1
    assert execution_service.calls[0]["prompt_text"] == "inspect the configs"
    assert shell_state.active_session_mode == SessionMode.NORMAL
    assert shell_state.active_session_public_id is not None
    assert build_prompt(shell_state).startswith("\nnormal:")
    assert "done" in captured["answers"]


def test_run_interactive_shell_redteam_command_sets_mode_and_next_plain_text_executes(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Redteam current",
        goal="Track redteam work",
        mode="redteam",
        status="active",
    )
    shell_state.bind_session(SessionSummary.from_session(session, reused=True))
    controller = AgentController.from_session_service(session_service)
    capability_service = main_module.create_capability_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    responses = iter(["/redteam", "Scan example.com for open services", "/quit"])

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
            capability_service=capability_service,
            input_func=fake_input,
        )
    )

    assert shell_state.requested_session_mode == SessionMode.REDTEAM
    assert shell_state.active_session_mode is not None
    assert shell_state.active_session_mode.value == "redteam"
    assert build_prompt(shell_state).startswith("\nredteam:")
    assert len(execution_service.calls) == 1
    assert execution_service.calls[0]["prompt_text"] == "Scan example.com for open services"


def test_run_interactive_shell_ctrl_d_exits_with_goodbye(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    capability_service = main_module.create_capability_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    headers: list[str] = []

    def fake_input(_prompt):
        raise EOFError

    monkeypatch.setattr(main_module.ColoredOutput, "print_header", headers.append)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            execution_service=execution_service,
            capability_service=capability_service,
            input_func=fake_input,
        )
    )

    assert headers == ["Goodbye"]
    assert execution_service.calls == []


def test_run_interactive_shell_ctrl_c_requires_confirmation(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    capability_service = main_module.create_capability_service()
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    headers: list[str] = []
    responses = iter([KeyboardInterrupt(), "n", KeyboardInterrupt(), "y"])

    def fake_input(_prompt):
        response = next(responses)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(main_module.ColoredOutput, "print_header", headers.append)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            session_service=session_service,
            controller=controller,
            execution_service=execution_service,
            capability_service=capability_service,
            input_func=fake_input,
        )
    )

    assert headers == ["Goodbye"]
    assert execution_service.calls == []


def test_run_interactive_shell_routes_explicit_module_request_to_module_runtime(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    capability_service = main_module.create_capability_service(settings)
    module_service = main_module.create_module_service(
        settings,
        capability_service=capability_service,
    )
    controller = AgentController.from_session_service(
        session_service,
        module_names=tuple(capability.manifest.name for capability in module_service.list_modules()),
    )
    execution_service = FakeExecutionService()
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"answers": []}
    responses = iter(["/module run surface-recon example.com", "/quit"])

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
            capability_service=capability_service,
            module_service=module_service,
            input_func=fake_input,
        )
    )

    assert execution_service.calls == []
    assert execution_service.module_calls == [
        {
            "module_name": "surface-recon",
            "parameters": {
                "target": "example.com",
                "include_dns": True,
                "include_http": True,
                "include_tls": True,
            },
            "one_shot": True,
        }
    ]
    assert "done" in captured["answers"]


def test_build_controller_request_and_clear_command_preserve_session_binding(tmp_path):
    session_state = SessionState()
    session_state.append_user_message("hello")
    shell_state = ShellState(
        requested_session_mode=SessionMode.REDTEAM,
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode=SessionMode.NORMAL,
        active_session_title="Session",
        active_session_target_summary="example.com",
        active_skill_name="security-audit",
    )

    request = build_controller_request(question="inspect configs", shell_state=shell_state)
    assert request.requested_session_mode == SessionMode.REDTEAM
    assert request.active_session_public_id == "S0001"
    assert request.record_query is None

    handle_clear_command("/clear", shell_state=shell_state, session_state=session_state)

    assert shell_state.active_session_public_id == "S0001"
    assert shell_state.active_session_mode == SessionMode.NORMAL
    assert shell_state.requested_session_mode == SessionMode.REDTEAM
    assert shell_state.active_skill_name == "security-audit"


def test_build_prompt_prefers_session_binding():
    shell_state = ShellState(
        requested_session_mode=SessionMode.NORMAL,
        active_session_id="session-1",
        active_session_public_id="S0001",
        active_session_mode=SessionMode.NORMAL,
    )

    assert build_prompt(shell_state) == "\nnormal:S0001 > "


def test_handle_redteam_and_normal_commands_set_requested_mode():
    shell_state = ShellState()
    outputs: list[str] = []
    presenter = main_module.CliPresenter.for_callbacks(
        info_output=outputs.append,
        success_output=outputs.append,
        error_output=outputs.append,
    )

    assert handle_redteam_command("/redteam", shell_state=shell_state, presenter=presenter)
    assert shell_state.requested_session_mode == SessionMode.REDTEAM
    assert handle_normal_command("/normal", shell_state=shell_state, presenter=presenter)
    assert shell_state.requested_session_mode == SessionMode.NORMAL
    assert any("Switched to redteam mode." in message for message in outputs)
    assert any("Switched to normal mode." in message for message in outputs)


def test_redteam_and_normal_commands_reject_arguments():
    shell_state = ShellState()
    errors: list[str] = []
    presenter = main_module.CliPresenter.for_callbacks(error_output=errors.append)

    assert handle_redteam_command("/redteam on", shell_state=shell_state, presenter=presenter)
    assert shell_state.requested_session_mode == SessionMode.NORMAL
    assert handle_normal_command("/normal now", shell_state=shell_state, presenter=presenter)
    assert shell_state.requested_session_mode == SessionMode.NORMAL
    assert any("Usage: /redteam" in message for message in errors)
    assert any("Usage: /normal" in message for message in errors)


def test_prompt_execution_confirmation_ctrl_c_defaults_to_deny():
    outputs: list[str] = []
    presenter = main_module.CliPresenter.for_callbacks(info_output=outputs.append)
    request = ConfirmationRequest(
        action_name="scan",
        risk_level="medium",
        target_summary="example.com",
        reason="test",
        message="Approve scan?",
        request_id="confirm-1",
    )

    def interrupted_input(_prompt):
        raise KeyboardInterrupt

    decision = prompt_execution_confirmation(
        request=request,
        input_func=interrupted_input,
        ui=presenter,
    )

    assert decision.request_id == "confirm-1"
    assert decision.decision == ConfirmationDecisionValue.DENY
    assert any("Confirmation required: scan" in output for output in outputs)


def test_build_controller_request_parses_record_query_commands():
    request = build_controller_request(
        question="/why F0001 latest",
        shell_state=ShellState(),
    )

    assert request.record_query is not None
    assert request.record_query.kind == RecordLookupKind.FINDING_EXPLANATION
    assert request.record_query.lookup_identifier == "F0001"
    assert request.record_query.explicit_scope == "latest"


def test_run_interactive_shell_rejects_removed_operation_job_and_evidence_commands(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    session_service = SessionService.from_settings(settings)
    controller = AgentController.from_session_service(session_service)
    capability_service = main_module.create_capability_service()
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
            capability_service=capability_service,
            input_func=fake_input,
        )
    )

    assert execution_service.calls == []
    assert any("Unknown command: /operation list" in message for message in errors)
    assert any("Unknown command: /job list S0001" in message for message in errors)
    assert any("Unknown command: /evidence list S0001" in message for message in errors)
