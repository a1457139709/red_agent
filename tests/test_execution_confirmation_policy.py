import asyncio
from dataclasses import dataclass

from agent.settings import Settings
from agent.state import SessionState
from app.execution_service import ExecutionService
from app.session_service import SessionService
from controller.contracts import ConfirmationDecision, ConfirmationDecisionValue, ConfirmationRequest
from models.conversation_context import ConversationContext
from models.risk_policy import RiskLevel
from models.session import SessionMode, SessionStatus
from runtime.execution_events import ExecutionEventType
from tools.executor import ToolExecutor
from tools.policy import RuntimeSafetyPolicy


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name

    def invoke(self, args):
        return f"ok:{self.name}"


@dataclass(slots=True)
class FakeRuntimeConfig:
    system_prompt: str
    allowed_tools: list[str]
    safety_policy: RuntimeSafetyPolicy
    preferred_shell: str | None = None

    def with_settings(self, settings: Settings) -> Settings:
        return settings


class FakeSkillService:
    def __init__(self, allowed_tools: list[str]) -> None:
        self.allowed_tools = allowed_tools

    async def build_base_runtime_config(self, *, context_summary: str) -> FakeRuntimeConfig:
        return FakeRuntimeConfig(
            system_prompt="base",
            allowed_tools=self.allowed_tools,
            safety_policy=RuntimeSafetyPolicy.base(),
        )

    async def build_skill_runtime_config(self, *, skill_name: str, context_summary: str) -> FakeRuntimeConfig:
        return await self.build_base_runtime_config(context_summary=context_summary)


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


class FakeInteractionPort:
    def __init__(self, *, approve: bool) -> None:
        self.approve = approve
        self.events = []
        self.confirmations: list[ConfirmationRequest] = []
        self.decisions: list[ConfirmationDecision] = []

    def emit_controller_result(self, result, context) -> None:
        return None

    def emit_execution_progress(self, event, context) -> None:
        self.events.append(event)

    def emit_final_answer(self, text, context) -> None:
        return None

    def emit_interaction_error(self, message, context) -> None:
        return None

    def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        self.confirmations.append(request)
        return ConfirmationDecision(
            request_id=request.request_id,
            decision=(
                ConfirmationDecisionValue.APPROVE
                if self.approve
                else ConfirmationDecisionValue.DENY
            ),
        )

    def emit_confirmation_resolved(self, decision, context) -> None:
        self.decisions.append(decision)


def test_execution_service_blocks_denied_confirmation_and_records_events(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Redteam Session",
        goal="Run dangerous action",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
    )

    async def fake_agent_loop(question, state, runtime_executor, current_settings, **kwargs):
        runtime_executor.execute("poc_execute", {})
        return {"status": "completed", "response": "done", "messages": [], "usage": {}}

    async def fake_apply_result_to_session(**kwargs):
        return None

    from runtime.foreground_runner import ForegroundRunner

    execution_service = ExecutionService(
        session_service=session_service,
        foreground_runner=ForegroundRunner(
            agent_loop_fn=fake_agent_loop,
            apply_result_to_session_fn=fake_apply_result_to_session,
        ),
        confirmation_policy_service=ExecutionService.from_settings(settings).confirmation_policy_service,
        tool_access_policy_service=ExecutionService.from_settings(settings).tool_access_policy_service,
    )
    interaction_port = FakeInteractionPort(approve=False)

    outcome = asyncio.run(
        execution_service.execute_session(
            session_identifier=session.id,
            prompt_text="run poc",
            session_state=SessionState(),
            skill_service=FakeSkillService(["poc_execute"]),
            tool_executor=ToolExecutor({"poc_execute": FakeTool("poc_execute")}),
            settings=settings,
            conversation_context=ConversationContext(),
            interaction_port=interaction_port,
        )
    )

    assert outcome.status == "blocked"
    assert len(interaction_port.confirmations) == 1
    assert [event.event_type for event in interaction_port.events if event.event_type in {
        ExecutionEventType.CONFIRMATION_REQUIRED,
        ExecutionEventType.CONFIRMATION_DENIED,
    }] == [
        ExecutionEventType.CONFIRMATION_REQUIRED,
        ExecutionEventType.CONFIRMATION_DENIED,
    ]
    refreshed = session_service.require_session(session.id)
    assert refreshed.status == SessionStatus.ACTIVE
    assert refreshed.last_error is not None


def test_execution_service_resumes_when_confirmation_is_approved(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Redteam Session",
        goal="Run dangerous action",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
    )

    async def fake_agent_loop(question, state, runtime_executor, current_settings, **kwargs):
        runtime_executor.execute("poc_execute", {})
        return {"status": "completed", "response": "done", "messages": [], "usage": {}}

    async def fake_apply_result_to_session(**kwargs):
        return None

    from runtime.foreground_runner import ForegroundRunner

    execution_service = ExecutionService(
        session_service=session_service,
        foreground_runner=ForegroundRunner(
            agent_loop_fn=fake_agent_loop,
            apply_result_to_session_fn=fake_apply_result_to_session,
        ),
        confirmation_policy_service=ExecutionService.from_settings(settings).confirmation_policy_service,
        tool_access_policy_service=ExecutionService.from_settings(settings).tool_access_policy_service,
    )
    interaction_port = FakeInteractionPort(approve=True)

    outcome = asyncio.run(
        execution_service.execute_session(
            session_identifier=session.id,
            prompt_text="run poc",
            session_state=SessionState(),
            skill_service=FakeSkillService(["poc_execute"]),
            tool_executor=ToolExecutor({"poc_execute": FakeTool("poc_execute")}),
            settings=settings,
            conversation_context=ConversationContext(),
            interaction_port=interaction_port,
        )
    )

    assert outcome.status == "completed"
    assert ExecutionEventType.CONFIRMATION_APPROVED in [
        event.event_type for event in interaction_port.events
    ]


def test_execution_service_requires_confirmation_for_unknown_redteam_action(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Redteam Session",
        goal="Run unknown action",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
    )

    async def fake_agent_loop(question, state, runtime_executor, current_settings, **kwargs):
        runtime_executor.execute("unknown_new_action", {"target": "example.com"})
        return {"status": "completed", "response": "done", "messages": [], "usage": {}}

    async def fake_apply_result_to_session(**kwargs):
        return None

    from runtime.foreground_runner import ForegroundRunner

    execution_service = ExecutionService(
        session_service=session_service,
        foreground_runner=ForegroundRunner(
            agent_loop_fn=fake_agent_loop,
            apply_result_to_session_fn=fake_apply_result_to_session,
        ),
        confirmation_policy_service=ExecutionService.from_settings(settings).confirmation_policy_service,
        tool_access_policy_service=ExecutionService.from_settings(settings).tool_access_policy_service,
    )
    interaction_port = FakeInteractionPort(approve=False)

    outcome = asyncio.run(
        execution_service.execute_session(
            session_identifier=session.id,
            prompt_text="run unknown action",
            session_state=SessionState(),
            skill_service=FakeSkillService(["unknown_new_action"]),
            tool_executor=ToolExecutor({"unknown_new_action": FakeTool("unknown_new_action")}),
            settings=settings,
            conversation_context=ConversationContext(),
            interaction_port=interaction_port,
        )
    )

    assert outcome.status == "blocked"
    assert len(interaction_port.confirmations) == 1
    assert interaction_port.confirmations[0].action_name == "unknown_new_action"
    assert interaction_port.confirmations[0].risk_level == RiskLevel.ELEVATED.value
    assert [event.event_type for event in interaction_port.events if event.event_type in {
        ExecutionEventType.CONFIRMATION_REQUIRED,
        ExecutionEventType.CONFIRMATION_DENIED,
    }] == [
        ExecutionEventType.CONFIRMATION_REQUIRED,
        ExecutionEventType.CONFIRMATION_DENIED,
    ]
