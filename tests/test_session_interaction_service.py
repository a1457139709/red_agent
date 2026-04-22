import asyncio

from agent.settings import Settings
from agent.state import SessionState
from app.execution_service import ExecutionService
from app.session_interaction_service import SessionInteractionService
from app.session_service import SessionService
from controller.agent_controller import AgentController
from controller.contracts import ConfirmationDecision, ConfirmationDecisionValue, ConfirmationRequest
from models.conversation_context import ConversationContext
from runtime.execution_events import ExecutionOutcome
from tools.executor import ToolExecutor


class FakeSkillService:
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

    def emit_controller_result(self, result, context) -> None:
        self.controller_results.append(result)

    def emit_execution_progress(self, event, context) -> None:
        return None

    def emit_final_answer(self, text, context) -> None:
        self.final_answers.append(text)

    def emit_interaction_error(self, message, context) -> None:
        self.errors.append(message)

    def request_confirmation(
        self,
        request: ConfirmationRequest,
        context: ConversationContext,
    ) -> ConfirmationDecision:
        return ConfirmationDecision(
            request_id=request.request_id,
            decision=ConfirmationDecisionValue.APPROVE,
        )

    def emit_confirmation_resolved(self, decision, context) -> None:
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
            skill_service=FakeSkillService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert outcome.controller_result is not None
    assert outcome.controller_result.session_summary is not None
    assert context.active_session_public_id == outcome.controller_result.session_summary.public_id
    assert interaction_port.final_answers == ["done"]


def test_session_interaction_service_preserves_clarification_between_turns(tmp_path):
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
            question="look at example.com",
            conversation_context=context,
            session_state=SessionState(),
            skill_service=FakeSkillService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert first.controller_result is not None
    assert context.pending_clarification is not None

    second = asyncio.run(
        interaction_service.handle_message(
            question="one-off check",
            conversation_context=context,
            session_state=SessionState(),
            skill_service=FakeSkillService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
            interaction_port=interaction_port,
        )
    )

    assert second.controller_result is not None
    assert context.pending_clarification is None
    assert context.active_session_public_id is not None
