import asyncio
from dataclasses import dataclass

from agent.settings import Settings
from agent.state import SessionState
from models.session import Session, SessionMode, SessionPersistenceMode, SessionStatus
from runtime.execution_events import ExecutionEventType
from runtime.foreground_runner import ForegroundRunner
from tools.executor import ToolExecutionGateDecision, ToolExecutor
from tools.policy import RuntimeSafetyPolicy


class FakeTool:
    name = "fake_tool"

    def invoke(self, args):
        return f"ok:{args.get('value', '')}"


@dataclass(slots=True)
class FakeRuntimeConfig:
    system_prompt: str
    allowed_tools: list[str]
    safety_policy: RuntimeSafetyPolicy
    preferred_shell: str | None = None
    skill: object | None = None

    def with_settings(self, settings: Settings) -> Settings:
        return settings


class FakeSkillService:
    def __init__(self) -> None:
        self.base_calls = 0
        self.skill_calls: list[str] = []

    async def build_base_runtime_config(self, *, context_summary: str) -> FakeRuntimeConfig:
        self.base_calls += 1
        return FakeRuntimeConfig(
            system_prompt="base",
            allowed_tools=["fake_tool"],
            safety_policy=RuntimeSafetyPolicy.base(),
        )

    async def build_skill_runtime_config(self, *, skill_name: str, context_summary: str) -> FakeRuntimeConfig:
        self.skill_calls.append(skill_name)
        return FakeRuntimeConfig(
            system_prompt=f"skill:{skill_name}",
            allowed_tools=["fake_tool"],
            safety_policy=RuntimeSafetyPolicy.base(),
        )


def build_settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_session(tmp_path) -> Session:
    session = Session.create(
        title="Session",
        goal="Goal",
        mode=SessionMode.NORMAL,
        persistence_mode=SessionPersistenceMode.EPHEMERAL,
        workspace=str(tmp_path),
        status=SessionStatus.ACTIVE,
    )
    session.public_id = "S0001"
    return session


def test_foreground_runner_emits_started_tool_and_completed_events(tmp_path):
    settings = build_settings(tmp_path)
    session = build_session(tmp_path)
    session_state = SessionState()
    skill_service = FakeSkillService()
    tool_executor = ToolExecutor({"fake_tool": FakeTool()})
    applied = {"count": 0}

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        runtime_executor.execute("fake_tool", {"value": "x"})
        return {
            "status": "completed",
            "response": "done",
            "messages": [],
            "usage": {"total_tokens": 8},
        }

    async def fake_apply_result_to_session(**kwargs):
        applied["count"] += 1

    runner = ForegroundRunner(
        agent_loop_fn=fake_agent_loop,
        apply_result_to_session_fn=fake_apply_result_to_session,
    )
    events = []
    outcome = asyncio.run(
        runner.run(
            session=session,
            prompt_text="inspect",
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            on_progress=events.append,
        )
    )

    assert outcome.is_completed
    assert outcome.response == "done"
    assert applied["count"] == 1
    assert skill_service.base_calls == 1
    assert [event.event_type for event in events] == [
        ExecutionEventType.EXECUTION_STARTED,
        ExecutionEventType.STEP_STARTED,
        ExecutionEventType.STEP_COMPLETED,
        ExecutionEventType.EXECUTION_COMPLETED,
    ]
    assert events[1].step_label == "fake_tool"


def test_foreground_runner_returns_failed_outcome_when_agent_loop_raises(tmp_path):
    settings = build_settings(tmp_path)
    session = build_session(tmp_path)
    session_state = SessionState()
    skill_service = FakeSkillService()
    tool_executor = ToolExecutor({"fake_tool": FakeTool()})

    async def failing_agent_loop(*args, **kwargs):
        raise RuntimeError("boom")

    async def fake_apply_result_to_session(**kwargs):
        raise AssertionError("apply_result_to_session should not run on failure")

    runner = ForegroundRunner(
        agent_loop_fn=failing_agent_loop,
        apply_result_to_session_fn=fake_apply_result_to_session,
    )
    events = []
    outcome = asyncio.run(
        runner.run(
            session=session,
            prompt_text="inspect",
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            on_progress=events.append,
        )
    )

    assert not outcome.is_completed
    assert outcome.status == "failed"
    assert outcome.error == "boom"
    assert events[0].event_type == ExecutionEventType.EXECUTION_STARTED
    assert events[-1].event_type == ExecutionEventType.EXECUTION_FAILED


def test_foreground_runner_maps_cancelled_agent_loop_to_paused_outcome(tmp_path):
    settings = build_settings(tmp_path)
    session = build_session(tmp_path)
    session_state = SessionState()
    skill_service = FakeSkillService()
    tool_executor = ToolExecutor({"fake_tool": FakeTool()})

    async def cancelled_agent_loop(*args, **kwargs):
        raise asyncio.CancelledError

    async def fake_apply_result_to_session(**kwargs):
        raise AssertionError("apply_result_to_session should not run on interruption")

    runner = ForegroundRunner(
        agent_loop_fn=cancelled_agent_loop,
        apply_result_to_session_fn=fake_apply_result_to_session,
    )
    events = []
    outcome = asyncio.run(
        runner.run(
            session=session,
            prompt_text="inspect",
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            on_progress=events.append,
        )
    )

    assert not outcome.is_completed
    assert outcome.status == "paused"
    assert outcome.error == "Foreground execution was interrupted before completion."
    assert [event.event_type for event in events] == [
        ExecutionEventType.EXECUTION_STARTED,
        ExecutionEventType.EXECUTION_PAUSED,
    ]
    assert events[-1].message == outcome.error


def test_foreground_runner_maps_non_completed_status_to_execution_failed(tmp_path):
    settings = build_settings(tmp_path)
    session = build_session(tmp_path)
    session_state = SessionState()
    skill_service = FakeSkillService()
    tool_executor = ToolExecutor({"fake_tool": FakeTool()})

    async def fake_agent_loop(*args, **kwargs):
        return {
            "status": "max_steps_exceeded",
            "response": "too long",
            "messages": [],
            "usage": {"total_tokens": 100},
        }

    async def fake_apply_result_to_session(**kwargs):
        return None

    runner = ForegroundRunner(
        agent_loop_fn=fake_agent_loop,
        apply_result_to_session_fn=fake_apply_result_to_session,
    )
    events = []
    outcome = asyncio.run(
        runner.run(
            session=session,
            prompt_text="inspect",
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            on_progress=events.append,
        )
    )

    assert outcome.status == "max_steps_exceeded"
    assert outcome.error == "too long"
    assert events[-1].event_type == ExecutionEventType.EXECUTION_FAILED


def test_foreground_runner_maps_gate_block_to_blocked_outcome(tmp_path):
    settings = build_settings(tmp_path)
    session = build_session(tmp_path)
    session_state = SessionState()
    skill_service = FakeSkillService()
    tool_executor = ToolExecutor({"fake_tool": FakeTool()})

    async def fake_agent_loop(*args, **kwargs):
        runtime_executor = args[2]
        runtime_executor.execute("fake_tool", {"value": "x"})
        return {"status": "completed", "response": "done", "messages": [], "usage": {}}

    async def fake_apply_result_to_session(**kwargs):
        return None

    runner = ForegroundRunner(
        agent_loop_fn=fake_agent_loop,
        apply_result_to_session_fn=fake_apply_result_to_session,
    )
    events = []
    outcome = asyncio.run(
        runner.run(
            session=session,
            prompt_text="inspect",
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            execution_gate=lambda request: ToolExecutionGateDecision(
                status="deny",
                reason="test_block",
                message="blocked by test gate",
            ),
            on_progress=events.append,
        )
    )

    assert outcome.status == "blocked"
    assert outcome.error == "blocked by test gate"
    assert events[-1].event_type == ExecutionEventType.EXECUTION_PAUSED
