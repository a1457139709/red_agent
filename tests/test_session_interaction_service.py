import asyncio

from agent.settings import Settings
from agent.state import SessionState
from app.execution_service import ExecutionService
from app.session_interaction_service import SessionInteractionService
from app.session_service import SessionService
from controller.agent_controller import AgentController
from controller.contracts import (
    ConfirmationDecision,
    ConfirmationDecisionValue,
    ConfirmationRequest,
    ControllerResultStatus,
)
from models.conversation_context import ConversationContext
from runtime.execution_events import ExecutionOutcome
from tools.executor import ToolExecutor


class FakeCapabilityService:
    pass


class FakeExecutionService:
    def __init__(self) -> None:
        self.calls = []

    async def execute_session(self, **kwargs) -> ExecutionOutcome:
        self.calls.append(kwargs)
        return ExecutionOutcome(status="completed", response="done")


class FakeInteractionPort:
    def __init__(self) -> None:
        self.controller_results = []
        self.final_answers = []
        self.errors = []

    async def emit_controller_result(self, result, context) -> None:
        self.controller_results.append(result)

    async def emit_execution_progress(self, event, context) -> None:
        return None

    async def emit_final_answer(self, text, context) -> None:
        self.final_answers.append(text)

    async def emit_interaction_error(self, message, context) -> None:
        self.errors.append(message)

    async def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        return ConfirmationDecision(
            request_id=request.request_id,
            decision=ConfirmationDecisionValue.APPROVE,
        )

    async def emit_confirmation_resolved(self, decision, context) -> None:
        return None


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_session_interaction_service_binds_session_and_executes(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    interaction_service = SessionInteractionService.from_services(
        controller=AgentController.from_session_service(session_service),
        execution_service=FakeExecutionService(),
    )
    context = ConversationContext(active_skill_name="security-audit")
    interaction_port = FakeInteractionPort()

    outcome = asyncio.run(
        interaction_service.handle_message(
            question="Summarize this repository",
            conversation_context=context,
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert outcome.controller_result is not None
    assert outcome.controller_result.session_summary is not None
    assert context.active_session_public_id == outcome.controller_result.session_summary.public_id
    assert interaction_port.final_answers == ["done"]


def test_session_interaction_service_returns_missing_fields_without_pending_state(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session_service.create_session(
        title="History Session",
        goal="Review history",
        mode="normal",
        status="active",
    )
    interaction_service = SessionInteractionService.from_services(
        controller=AgentController.from_session_service(session_service),
        execution_service=FakeExecutionService(),
    )
    context = ConversationContext()
    interaction_port = FakeInteractionPort()

    first = asyncio.run(
        interaction_service.handle_message(
            question="what did you already do?",
            conversation_context=context,
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert first.controller_result is not None
    assert first.controller_result.status == ControllerResultStatus.MISSING_FIELDS
    assert first.controller_result.missing_field_error is not None
    assert first.controller_result.missing_field_error.missing_fields == ["session_scope"]

    second = asyncio.run(
        interaction_service.handle_message(
            question="/status latest",
            conversation_context=context,
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert second.controller_result is not None
    assert second.controller_result.record_lookup_payload is not None


def test_session_interaction_service_advanced_command_after_missing_fields_is_independent(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    interaction_service = SessionInteractionService.from_services(
        controller=AgentController.from_session_service(session_service),
        execution_service=FakeExecutionService(),
    )
    context = ConversationContext()
    interaction_port = FakeInteractionPort()

    first = asyncio.run(
        interaction_service.handle_message(
            question="/findings",
            conversation_context=context,
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert first.controller_result is not None
    assert first.controller_result.status == ControllerResultStatus.MISSING_FIELDS

    second = asyncio.run(
        interaction_service.handle_message(
            question="/help findings",
            conversation_context=context,
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert second.advanced_command_delegated
    assert second.controller_result is not None
    assert second.controller_result.status == ControllerResultStatus.DELEGATED_TO_ADVANCED_COMMAND
