from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from langchain_core.messages import AIMessage, ToolMessage

import agent.loop as loop_module
from agent.settings import Settings
from agent.state import SessionState
from app.skill_service import SkillService
from skills.registry import SkillRegistry
from tools import build_tool_registry
from tools.executor import ToolExecutor


class FakeWeatherModel:
    def __init__(self, command: str) -> None:
        self.command = command
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if self.calls == 0:
            self.calls += 1
            return AIMessage(
                content="I should run the local weather script first.",
                tool_calls=[
                    {
                        "name": "bash",
                        "args": {"command": self.command},
                        "id": "weather_call_1",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={"input_tokens": 10, "output_tokens": 6, "total_tokens": 16},
            )

        tool_message = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
        self.calls += 1
        return AIMessage(
            content=f"The example weather is: {tool_message.content}",
            tool_calls=[],
            usage_metadata={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
        )


def test_weather_query_example_skill_loads_and_completes_query(monkeypatch):
    tool_registry = build_tool_registry()
    skill_service = SkillService(
        SkillRegistry.built_in(known_tool_names=set(tool_registry.keys())),
        base_tool_names=list(tool_registry.keys()),
        default_task_skill_name=None,
    )
    runtime_config = asyncio.run(
        skill_service.build_skill_runtime_config(
            skill_name="weather-query-example",
            context_summary="",
        )
    )
    session_state = SessionState()
    executor = ToolExecutor(tool_registry)
    visible_executor = executor.restricted_to(runtime_config.allowed_tools).with_safety_policy(
        runtime_config.safety_policy
    )
    script_path = (
        Path(__file__).resolve().parent
        / "skills"
        / "weather-query-example"
        / "scripts"
        / "weather_lookup.py"
    )
    command = f'"{sys.executable}" "{script_path}" --city "Shanghai"'

    monkeypatch.setattr(loop_module, "log_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(loop_module, "create_model", lambda settings: FakeWeatherModel(command))

    result = asyncio.run(
        loop_module.agent_loop(
            "What is the weather in Shanghai?",
            session_state,
            visible_executor,
            Settings(
                openai_api_key="key",
                openai_api_base="https://example.com",
                openai_model="test-model",
            ),
            system_prompt=runtime_config.system_prompt,
            tools=visible_executor.get_tools(),
        )
    )

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]

    assert runtime_config.skill is not None
    assert runtime_config.skill.manifest.name == "weather-query-example"
    assert runtime_config.allowed_tools == ["bash", "list_dir", "read_file"]
    assert "Weather Query Example" in runtime_config.system_prompt
    assert result["status"] == "completed"
    assert tool_messages
    assert "Shanghai: 22C, Sunny, humidity 48%" in tool_messages[0].content
    assert "Shanghai: 22C, Sunny, humidity 48%" in result["response"]
