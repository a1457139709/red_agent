import asyncio

from agent.settings import Settings
from agent.state import SessionState
from app.execution_service import ExecutionService
from app.session_service import SessionService
from models.session import SessionMode, SessionStatus
from runtime.execution_events import ExecutionOutcome
from tools.executor import ToolExecutor


class FakeForegroundRunner:
    def __init__(self, outcome: ExecutionOutcome) -> None:
        self.outcome = outcome
        self.calls = 0
        self.last_session_status: SessionStatus | None = None

    async def run(self, **kwargs) -> ExecutionOutcome:
        self.calls += 1
        self.last_session_status = kwargs["session"].status
        return self.outcome


class FakeSkillService:
    pass


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_tool_executor() -> ToolExecutor:
    return ToolExecutor({})


def test_execution_service_sets_session_active_and_clears_last_error_on_success(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Session",
        goal="Goal",
        mode=SessionMode.NORMAL,
        status=SessionStatus.PAUSED,
    )
    session_service.update_session_status(session.id, SessionStatus.FAILED, last_error="old error")
    # Recreate a runnable session to satisfy transition rules.
    session = session_service.create_session(
        title="Session 2",
        goal="Goal",
        mode=SessionMode.NORMAL,
        status=SessionStatus.ACTIVE,
    )
    session_service.update_session_status(session.id, SessionStatus.ACTIVE, last_error="old error")
    runner = FakeForegroundRunner(ExecutionOutcome(status="completed", response="done"))
    service = ExecutionService(session_service=session_service, foreground_runner=runner)

    outcome = asyncio.run(
        service.execute_session(
            session_identifier=session.id,
            prompt_text="inspect",
            session_state=SessionState(),
            skill_service=FakeSkillService(),
            tool_executor=build_tool_executor(),
            settings=settings,
        )
    )

    refreshed = session_service.require_session(session.id)
    assert outcome.is_completed
    assert runner.calls == 1
    assert runner.last_session_status == SessionStatus.ACTIVE
    assert refreshed.status == SessionStatus.ACTIVE
    assert refreshed.last_error is None


def test_execution_service_persists_last_error_and_keeps_active_on_failure(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    session = session_service.create_session(
        title="Session",
        goal="Goal",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
    )
    runner = FakeForegroundRunner(
        ExecutionOutcome(
            status="failed",
            response="boom",
            error="boom",
        )
    )
    service = ExecutionService(session_service=session_service, foreground_runner=runner)

    outcome = asyncio.run(
        service.execute_session(
            session_identifier=session.id,
            prompt_text="inspect",
            session_state=SessionState(),
            skill_service=FakeSkillService(),
            tool_executor=build_tool_executor(),
            settings=settings,
        )
    )

    refreshed = session_service.require_session(session.id)
    assert not outcome.is_completed
    assert outcome.error == "boom"
    assert refreshed.status == SessionStatus.ACTIVE
    assert refreshed.last_error == "boom"


def test_execution_service_returns_failed_outcome_for_missing_session(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    service = ExecutionService(
        session_service=session_service,
        foreground_runner=FakeForegroundRunner(ExecutionOutcome(status="completed", response="unused")),
    )

    outcome = asyncio.run(
        service.execute_session(
            session_identifier="S9999",
            prompt_text="inspect",
            session_state=SessionState(),
            skill_service=FakeSkillService(),
            tool_executor=build_tool_executor(),
            settings=settings,
        )
    )

    assert outcome.status == "failed"
    assert outcome.error is not None
