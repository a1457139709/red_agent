import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

import agent.context as context_module
from agent.context import (
    CompressionSummary,
    build_compressed_context,
    compress_context,
    render_history_for_compression,
)
from agent.settings import Settings
from agent.state import SessionState


def test_session_state_apply_compressed_summary_clears_history():
    state = SessionState()
    state.append_user_message("hello")

    state.apply_compressed_summary("summary text")

    assert state.history == []
    assert state.context_summary == "summary text"


def test_compression_summary_parses_xmlish_text():
    raw = """
    <completed>
    edited src/main.py
    </completed>
    <remaining>
    add tests
    </remaining>
    <current_state>
    branch is clean
    </current_state>
    <notes>
    do not touch .env
    </notes>
    """.strip()

    summary = CompressionSummary.from_text(raw)
    rendered = build_compressed_context(summary)

    assert summary.completed == "edited src/main.py"
    assert summary.remaining == "add tests"
    assert "do not touch .env" in rendered


def test_render_history_for_compression_includes_tool_calls_and_observations():
    history = [
        HumanMessage(content="inspect the config"),
        AIMessage(
            content="I will read the file first.",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"file_path": "README.md"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="line 1\nline 2", tool_call_id="call_1"),
    ]

    rendered = render_history_for_compression(history)

    assert "assistant_tool_call" in rendered
    assert "tool_observation" in rendered
    assert "tool_name: read_file" in rendered
    assert "tool_call_id: call_1" in rendered
    assert '"file_path": "README.md"' in rendered
    assert "line 1" in rendered


def test_render_history_for_compression_truncates_long_tool_observations():
    long_observation = "A" * 1400
    history = [
        AIMessage(
            content="need output",
            tool_calls=[
                {
                    "name": "bash",
                    "args": {"command": "echo test"},
                    "id": "call_2",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content=long_observation, tool_call_id="call_2"),
    ]

    rendered = render_history_for_compression(history)

    assert "tool_name: bash" in rendered
    assert "tool_call_id: call_2" in rendered
    assert "result:\n" in rendered
    assert "..." in rendered
    assert long_observation not in rendered
    assert "A" * 200 in rendered


def test_compress_context_sends_tool_observations_to_model(monkeypatch):
    captured_messages = []

    class FakeCompressionModel:
        async def ainvoke(self, messages):
            captured_messages.extend(messages)
            return AIMessage(
                content="""
                <completed>
                read docs/guide.md
                </completed>
                <remaining>
                add tests
                </remaining>
                <current_state>
                summary prepared
                </current_state>
                <notes>
                keep tool observations
                </notes>
                """.strip(),
                tool_calls=[],
            )

    monkeypatch.setattr(context_module, "create_model", lambda settings: FakeCompressionModel())

    history = [
        HumanMessage(content="check the docs"),
        AIMessage(
            content="Reading docs now.",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"file_path": "docs/guide.md"},
                    "id": "call_3",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="Guide contents", tool_call_id="call_3"),
    ]

    settings = Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
    )
    summary = asyncio.run(compress_context(history, settings))

    assert summary.completed == "read docs/guide.md"
    assert len(captured_messages) == 2
    assert "tool_observation" in captured_messages[1].content
    assert "tool_name: read_file" in captured_messages[1].content
    assert "tool_call_id: call_3" in captured_messages[1].content
    assert "Guide contents" in captured_messages[1].content


def test_session_state_checkpoint_round_trip():
    state = SessionState()
    state.history = [
        SystemMessage(content="system"),
        AIMessage(
            content="need tool",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "README.md"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
            usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        ),
        ToolMessage(content="file content", tool_call_id="call_1"),
    ]
    state.compressed_summary = "summary"
    state.last_usage = {"total_tokens": 10}

    payload = state.to_checkpoint_payload()
    restored = SessionState.from_checkpoint_payload(payload)

    assert restored.compressed_summary == "summary"
    assert restored.last_usage == {"total_tokens": 10}
    assert len(restored.history) == 3
    assert isinstance(restored.history[0], SystemMessage)
    assert isinstance(restored.history[1], AIMessage)
    assert restored.history[1].tool_calls[0]["name"] == "read_file"
    assert isinstance(restored.history[2], ToolMessage)
    assert restored.history[2].tool_call_id == "call_1"
