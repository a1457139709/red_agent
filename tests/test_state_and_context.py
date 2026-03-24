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
