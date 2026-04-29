import asyncio

from agent.settings import Settings
from agent.state import SessionState
from app.dashboard_service import DashboardService
from app.report_flow_service import ReportFlowService
from app.session_interaction_service import SessionInteractionService
from app.session_record_query_service import SessionRecordQueryService
from app.session_service import SessionService
from controller.agent_controller import AgentController
from controller.contracts import ConfirmationDecisionValue, ConfirmationRequest
from models.run import utc_now_iso
from runtime.execution_events import ExecutionOutcome
from runtime.execution_events import ExecutionEventType, ExecutionProgressEvent
from tools.executor import ToolExecutor
from web.conversation_store import InMemoryConversationStore
from web.interaction_adapter import WebInteractionAdapter


class FakeExecutionService:
    async def execute_session(self, **kwargs) -> ExecutionOutcome:
        return ExecutionOutcome(status="completed", response="done")


class ConfirmationExecutionService:
    async def execute_session(self, **kwargs) -> ExecutionOutcome:
        interaction_port = kwargs["interaction_port"]
        context = kwargs["conversation_context"]
        await interaction_port.emit_execution_progress(
            ExecutionProgressEvent(
                event_type=ExecutionEventType.EXECUTION_STARTED,
                session_id=context.active_session_id or "session-1",
                session_public_id=context.active_session_public_id or "S0001",
                message="Foreground execution started.",
                timestamp=utc_now_iso(),
            ),
            context,
        )
        decision = await interaction_port.request_confirmation(
            ConfirmationRequest(
                action_name="poc_execute",
                risk_level="dangerous",
                target_summary=context.active_session_target_summary,
                reason="needs approval",
                message="Approve dangerous execution?",
            ),
            context,
        )
        await interaction_port.emit_confirmation_resolved(decision, context)
        return ExecutionOutcome(
            status="completed",
            response=f"decision:{decision.decision.value}",
        )


class FakeCapabilityService:
    pass


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_web_interaction_adapter_emits_ordered_events(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    adapter = WebInteractionAdapter(
        interaction_service=SessionInteractionService.from_services(
            controller=AgentController.from_session_service(session_service),
            execution_service=FakeExecutionService(),
        ),
        session_service=session_service,
        session_record_query_service=SessionRecordQueryService.from_settings(settings),
        report_flow_service=ReportFlowService.from_settings(settings),
        dashboard_service=DashboardService.from_settings(settings),
        conversation_store=InMemoryConversationStore(),
    )
    conversation = adapter.create_conversation()

    response = asyncio.run(
        adapter.handle_message(
            conversation_id=conversation.conversation_id,
            raw_input="Summarize this repository",
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
        )
    )

    assert response.controller_result is not None
    assert [event.sequence for event in response.events] == [1, 2]
    assert response.events[0].event_kind == "controller_result"
    assert response.events[1].event_kind == "final_answer"


def test_web_interaction_adapter_streams_confirmation_before_completion(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    adapter = WebInteractionAdapter(
        interaction_service=SessionInteractionService.from_services(
            controller=AgentController.from_session_service(session_service),
            execution_service=ConfirmationExecutionService(),
        ),
        session_service=session_service,
        session_record_query_service=SessionRecordQueryService.from_settings(settings),
        report_flow_service=ReportFlowService.from_settings(settings),
        dashboard_service=DashboardService.from_settings(settings),
        conversation_store=InMemoryConversationStore(),
    )
    conversation = adapter.create_conversation()

    async def run_flow():
        stream = await adapter.start_message(
            conversation_id=conversation.conversation_id,
            raw_input="Summarize this repository",
            session_state=SessionState(),
            capability_service=FakeCapabilityService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
        )
        first = await stream.receive_event()
        second = await stream.receive_event()
        third = await stream.receive_event()
        assert first is not None
        assert second is not None
        assert third is not None
        assert first.event_kind == "controller_result"
        assert second.event_kind == "execution_progress"
        assert third.event_kind == "confirmation_required"

        request_id = third.payload["request_id"]
        adapter.submit_confirmation(
            conversation_id=conversation.conversation_id,
            request_id=request_id,
            decision=ConfirmationDecisionValue.APPROVE.value,
        )

        fourth = await stream.receive_event()
        fifth = await stream.receive_event()
        response = await stream.wait()
        terminal = await stream.receive_event()
        return fourth, fifth, response, terminal

    fourth, fifth, response, terminal = asyncio.run(run_flow())

    assert fourth is not None
    assert fifth is not None
    assert fourth.event_kind == "confirmation_resolved"
    assert fifth.event_kind == "final_answer"
    assert response.final_text == "decision:approve"
    assert terminal is None
