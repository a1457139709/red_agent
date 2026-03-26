from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from agent.context import CompressionSummary, build_compressed_context
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
