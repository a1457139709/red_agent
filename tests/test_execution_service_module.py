import asyncio
import json
from pathlib import Path

from agent.settings import Settings
from app.capability_service import CapabilityService
from app.execution_service import ExecutionService
from app.module_service import ModuleService
from app.session_service import SessionService
from capabilities.registry import CapabilityRegistry
from controller.contracts import ConfirmationDecision, ConfirmationDecisionValue, ConfirmationRequest
from models.conversation_context import ConversationContext
from models.risk_policy import RiskLevel
from models.session import SessionMode, SessionStatus, SessionTarget, SessionTargetKind
from runtime.execution_events import ExecutionEventType
from runtime.foreground_runner import ForegroundRunner
from tools import build_tool_registry
from tools.executor import ToolExecutor


class FakeTool:
    def __init__(self, name: str, calls: list[tuple[str, dict]]) -> None:
        self.name = name
        self.calls = calls

    def invoke(self, args):
        self.calls.append((self.name, dict(args)))
        return f"ok:{self.name}:{args.get('target')}"


class RecordingInteractionPort:
    def __init__(self, *, approve_confirmation: bool = True) -> None:
        self.approve_confirmation = approve_confirmation
        self.events = []
        self.confirmation_requests: list[ConfirmationRequest] = []
        self.confirmation_decisions: list[ConfirmationDecision] = []

    async def emit_controller_result(self, result, context) -> None:
        return None

    async def emit_execution_progress(self, event, context) -> None:
        self.events.append(event)

    async def emit_final_answer(self, text, context) -> None:
        return None

    async def emit_interaction_error(self, message, context) -> None:
        return None

    async def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        self.confirmation_requests.append(request)
        return ConfirmationDecision(
            request_id=request.request_id,
            decision=(
                ConfirmationDecisionValue.APPROVE
                if self.approve_confirmation
                else ConfirmationDecisionValue.DENY
            ),
        )

    async def emit_confirmation_resolved(self, decision, context) -> None:
        self.confirmation_decisions.append(decision)


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_module_service(root: Path | None = None) -> ModuleService:
    known_tool_names = set(build_tool_registry().keys()) | {"port_scan"}
    registry = (
        CapabilityRegistry.built_in(known_tool_names=known_tool_names)
        if root is None
        else CapabilityRegistry(root, known_tool_names=known_tool_names)
    )
    return ModuleService(CapabilityService(registry))


def build_tool_executor(*names: str, calls: list[tuple[str, dict]] | None = None) -> ToolExecutor:
    call_log = calls if calls is not None else []
    return ToolExecutor({name: FakeTool(name, call_log) for name in names})


def write_port_scan_module(root: Path) -> None:
    directory = root / "port-scan"
    directory.mkdir(parents=True)
    payload = {
        "version": 1,
        "name": "port-scan",
        "kind": "module",
        "display_name": "Port Scan",
        "description": "Run a typed port scan.",
        "modes": ["redteam"],
        "parameters": [
            {
                "name": "target",
                "type": "string",
                "required": True,
                "description": "Target.",
            },
            {
                "name": "ports",
                "type": "array",
                "required": True,
                "description": "Ports.",
            },
        ],
        "tools": {"allowed": ["port_scan"]},
        "risk": {"default": "elevated", "actions": ["port_scan"]},
        "execution": {"style": "typed_tool", "profile": "port_scan"},
        "session": {
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": ["artifacts"],
        },
    }
    (directory / "capability.json").write_text(json.dumps(payload), encoding="utf-8")


def test_execute_one_shot_surface_recon_runs_typed_workflow_without_operation_id(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    execution_service = ExecutionService(
        session_service=session_service,
        foreground_runner=ForegroundRunner(),
    )
    module_service = build_module_service()
    invocation = module_service.prepare_invocation(
        module_name="surface-recon",
        parameters={"target": "example.com"},
        mode=SessionMode.REDTEAM,
        one_shot=True,
    )
    calls: list[tuple[str, dict]] = []

    outcome = asyncio.run(
        execution_service.execute_module(
            invocation=invocation,
            tool_executor=build_tool_executor("dns_lookup", "http_probe", "tls_inspect", calls=calls),
        )
    )

    assert outcome.status == "completed"
    assert calls == [
        ("dns_lookup", {"target": "example.com", "record_type": "A"}),
        ("http_probe", {"target": "http://example.com", "method": "GET"}),
        ("http_probe", {"target": "https://example.com", "method": "GET"}),
        ("tls_inspect", {"target": "example.com:443"}),
    ]
    assert outcome.raw_result is not None
    assert outcome.raw_result["one_shot"] is True
    assert "operation_id" not in json.dumps(outcome.raw_result)


def test_execute_persistent_module_uses_session_scope_and_records_error(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Scoped",
        goal="Only example.com is in scope",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
        targets=[SessionTarget(kind=SessionTargetKind.DOMAIN, value="example.com")],
    )
    execution_service = ExecutionService(
        session_service=session_service,
        foreground_runner=ForegroundRunner(),
    )
    module_service = build_module_service()
    invocation = module_service.prepare_invocation(
        module_name="surface-recon",
        parameters={"target": "evil.test", "include_dns": False},
        mode=SessionMode.REDTEAM,
        one_shot=False,
        session=session,
    )
    calls: list[tuple[str, dict]] = []

    outcome = asyncio.run(
        execution_service.execute_module(
            invocation=invocation,
            tool_executor=build_tool_executor("dns_lookup", "http_probe", "tls_inspect", calls=calls),
        )
    )

    assert outcome.status == "blocked"
    assert "outside the allowed domains" in (outcome.error or "")
    assert calls == []
    refreshed = session_service.require_session(session.id)
    assert refreshed.status == SessionStatus.ACTIVE
    assert refreshed.last_error is not None


def test_execute_typed_tool_module_uses_phase4_confirmation_policy(tmp_path):
    write_port_scan_module(tmp_path)
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Port scan",
        goal="Scan target",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
        targets=[SessionTarget(kind=SessionTargetKind.DOMAIN, value="example.com")],
    )
    execution_service = ExecutionService(
        session_service=session_service,
        foreground_runner=ForegroundRunner(),
    )
    module_service = build_module_service(tmp_path)
    invocation = module_service.prepare_invocation(
        module_name="port-scan",
        parameters={"target": "example.com", "ports": list(range(1, 150))},
        mode=SessionMode.REDTEAM,
        one_shot=False,
        session=session,
    )
    interaction_port = RecordingInteractionPort(approve_confirmation=False)
    calls: list[tuple[str, dict]] = []

    outcome = asyncio.run(
        execution_service.execute_module(
            invocation=invocation,
            tool_executor=build_tool_executor("port_scan", calls=calls),
            conversation_context=ConversationContext(),
            interaction_port=interaction_port,
        )
    )

    assert outcome.status == "blocked"
    assert calls == []
    assert len(interaction_port.confirmation_requests) == 1
    assert interaction_port.confirmation_requests[0].action_name == "port_scan"
    assert interaction_port.confirmation_requests[0].risk_level == RiskLevel.ELEVATED.value
    assert [
        event.event_type
        for event in interaction_port.events
        if event.event_type
        in {ExecutionEventType.CONFIRMATION_REQUIRED, ExecutionEventType.CONFIRMATION_DENIED}
    ] == [
        ExecutionEventType.CONFIRMATION_REQUIRED,
        ExecutionEventType.CONFIRMATION_DENIED,
    ]
