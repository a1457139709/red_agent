import asyncio

from langchain_core.messages import AIMessage, ToolMessage

import agent.loop as loop_module
from agent.settings import Settings
from agent.state import SessionState
from tools.executor import ToolExecutor


USAGE = {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}
USAGE_DONE = {"input_tokens": 6, "output_tokens": 6, "total_tokens": 12}


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name

    def invoke(self, args: dict) -> str:
        return f"ok:{self.name}:{args}"


class FakeModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return self.responses.pop(0)


def test_agent_loop_handles_multi_tool_calls_without_duplicate_ai_messages(monkeypatch):
    settings = Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        max_agent_steps=3,
    )
    state = SessionState()
    executor = ToolExecutor({"tool_a": FakeTool("tool_a"), "tool_b": FakeTool("tool_b")})
    responses = [
        AIMessage(
            content="need tools",
            tool_calls=[
                {"name": "tool_a", "args": {"x": 1}, "id": "call_a", "type": "tool_call"},
                {"name": "tool_b", "args": {"y": 2}, "id": "call_b", "type": "tool_call"},
            ],
            usage_metadata=USAGE,
        ),
        AIMessage(content="done", tool_calls=[], usage_metadata=USAGE_DONE),
    ]

    monkeypatch.setattr(loop_module, "log_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(loop_module, "create_model", lambda settings: FakeModel(responses))

    async def fake_prompt(extra):
        return "system prompt"

    monkeypatch.setattr(loop_module, "assemble_system_prompt", fake_prompt)

    result = asyncio.run(loop_module.agent_loop("question", state, executor, settings))
    ai_messages = [message for message in result["messages"] if isinstance(message, AIMessage)]
    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]

    assert result["status"] == "completed"
    assert len(ai_messages) == 2
    assert len(tool_messages) == 2


def test_agent_loop_returns_max_steps_exceeded(monkeypatch):
    settings = Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        max_agent_steps=2,
    )
    state = SessionState()
    executor = ToolExecutor({"tool_a": FakeTool("tool_a")})
    responses = [
        AIMessage(
            content="loop",
            tool_calls=[{"name": "tool_a", "args": {}, "id": f"loop_{i}", "type": "tool_call"}],
            usage_metadata=USAGE,
        )
        for i in range(settings.max_agent_steps)
    ]

    monkeypatch.setattr(loop_module, "log_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(loop_module, "create_model", lambda settings: FakeModel(responses))

    async def fake_prompt(extra):
        return "system prompt"

    monkeypatch.setattr(loop_module, "assemble_system_prompt", fake_prompt)

    result = asyncio.run(loop_module.agent_loop("question", state, executor, settings))

    assert result["status"] == "max_steps_exceeded"
    assert "任务在 2 步内仍未完成" in result["response"]
