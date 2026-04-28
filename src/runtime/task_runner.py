from __future__ import annotations

from collections.abc import Callable

from agent.context import build_compressed_context, compress_context, should_compress
from agent.settings import Settings
from agent.state import SessionState


InfoCallback = Callable[[str], None] | None


async def apply_result_to_session(
    *,
    question: str,
    result: dict,
    session_state: SessionState,
    settings: Settings,
    on_info: InfoCallback = None,
    on_error: InfoCallback = None,
) -> None:
    usage = result.get("usage") or {}

    session_state.append_user_message(question)
    session_state.append_messages(result["messages"])
    session_state.set_usage(usage)

    # Compress only after the latest exchange has been appended so the next turn
    # can resume from a summary that already includes this run.
    total_tokens = usage.get("total_tokens")
    if total_tokens is None or not should_compress(total_tokens, settings):
        return

    if on_info is not None:
        on_info("Context window is getting full, compressing session state...")

    try:
        summary = await compress_context(session_state.history, settings)
        hint = build_compressed_context(summary)
        session_state.apply_compressed_summary(hint)
        if on_info is not None:
            on_info("Context compressed. Future prompts will continue from the summary.")
    except Exception as exc:
        if on_error is not None:
            on_error(str(exc))
