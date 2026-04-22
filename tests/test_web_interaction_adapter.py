import asyncio

from agent.settings import Settings
from agent.state import SessionState
from app.dashboard_service import DashboardService
from app.report_flow_service import ReportFlowService
from app.session_interaction_service import SessionInteractionService
from app.session_record_query_service import SessionRecordQueryService
from app.session_service import SessionService
from app.skill_service import SkillService
from controller.agent_controller import AgentController
from runtime.execution_events import ExecutionOutcome
from tools.executor import ToolExecutor
from web.conversation_store import InMemoryConversationStore
from web.interaction_adapter import WebInteractionAdapter


class FakeExecutionService:
    async def execute_session(self, **kwargs) -> ExecutionOutcome:
        return ExecutionOutcome(status="completed", response="done")


class FakeSkillService:
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
            skill_service=FakeSkillService(),
            tool_executor=ToolExecutor({}),
            settings=settings,
        )
    )

    assert response.controller_result is not None
    assert [event.sequence for event in response.events] == [1, 2]
    assert response.events[0].event_kind == "controller_result"
    assert response.events[1].event_kind == "final_answer"
