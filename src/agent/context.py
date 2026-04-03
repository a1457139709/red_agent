from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .provider import create_model
from .settings import (
    DEFAULT_COMPRESSION_THRESHOLD,
    DEFAULT_CONTEXT_TOKEN_LIMIT,
    Settings,
    get_settings,
)

CHARS_PER_TOKEN = 3
MODEL_CONTEXT_TOKEN_LIMIT = DEFAULT_CONTEXT_TOKEN_LIMIT
COMPRESSION_THRESHOLD = DEFAULT_COMPRESSION_THRESHOLD
MAX_TOOL_ARGS_CHARS = 240
MAX_TOOL_OBSERVATION_CHARS = 1200
MAX_MESSAGE_CONTENT_CHARS = 2000

COMPRESS_SYSTEM = """
You compress an agent's execution history into a compact working summary.

Read the full conversation and produce XML using exactly these tags:

<completed>
Concrete work that is already done. Keep key file paths, commands, and tool-backed facts.
</completed>

<remaining>
Outstanding tasks, follow-ups, or blocked work.
</remaining>

<current_state>
The current working state: edited files, discovered facts, partial outputs, and relevant environment state.
</current_state>

<notes>
Important cautions, failed attempts, tool observations, evidence, error messages, and constraints that may affect future steps.
</notes>

Requirements:
- High information density, no filler.
- Preserve tool observations that matter for continuing the task.
- Include concrete evidence from tool outputs, file reads, command results, and errors when they affect next steps.
- Prefer short bullet-style lines inside each section.
- Do not invent facts that are not present in the history.
""".strip()

CONTEXT_TEMPLATE = """
Below is the compressed execution summary.

<completed>
{completed}
</completed>

<remaining>
{remaining}
</remaining>

<current_state>
{current_state}
</current_state>

<notes>
{notes}
</notes>

Use this summary as recovered working context for the next turn.
""".strip()


@dataclass
class CompressionSummary:
    completed: str = ""
    remaining: str = ""
    current_state: str = ""
    notes: str = ""

    @classmethod
    def from_text(cls, text: str) -> "CompressionSummary":
        def extract(tag: str) -> str:
            match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.DOTALL)
            return match.group(1).strip() if match else ""

        summary = cls(
            completed=extract("completed"),
            remaining=extract("remaining"),
            current_state=extract("current_state"),
            notes=extract("notes"),
        )

        if not any([summary.completed, summary.remaining, summary.current_state, summary.notes]):
            summary.notes = text.strip()

        return summary


def estimate_token(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def should_compress(current_tokens: int, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return current_tokens > settings.context_token_limit * settings.compression_threshold


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _truncate_text(value: str, *, limit: int) -> str:
    text = re.sub(r"\s+\n", "\n", value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _summarize_tool_args(args: Any) -> str:
    if not isinstance(args, dict):
        return _truncate_text(_stringify_content(args), limit=MAX_TOOL_ARGS_CHARS)

    compact: dict[str, Any] = {}
    for key, value in sorted(args.items()):
        if isinstance(value, str):
            compact[key] = _truncate_text(value, limit=120)
        else:
            compact[key] = value
    return _truncate_text(
        json.dumps(compact, ensure_ascii=False, sort_keys=True),
        limit=MAX_TOOL_ARGS_CHARS,
    )


def render_history_for_compression(history: list[BaseMessage]) -> str:
    parts: list[str] = []
    tool_calls_by_id: dict[str, dict[str, Any]] = {}

    for message in history:
        if isinstance(message, HumanMessage):
            parts.append(f"user\n{_truncate_text(_stringify_content(message.content), limit=MAX_MESSAGE_CONTENT_CHARS)}")
            continue

        if isinstance(message, AIMessage):
            content = _truncate_text(_stringify_content(message.content), limit=MAX_MESSAGE_CONTENT_CHARS)
            parts.append(f"assistant\n{content}")
            for tool_call in message.tool_calls:
                call_id = tool_call.get("id")
                if isinstance(call_id, str) and call_id:
                    tool_calls_by_id[call_id] = tool_call
                tool_name = tool_call.get("name", "unknown_tool")
                args_summary = _summarize_tool_args(tool_call.get("args", {}))
                parts.append(
                    "\n".join(
                        [
                            "assistant_tool_call",
                            f"tool_name: {tool_name}",
                            f"tool_call_id: {call_id or 'unknown'}",
                            f"args: {args_summary}",
                        ]
                    )
                )
            continue

        if isinstance(message, ToolMessage):
            tool_call = tool_calls_by_id.get(message.tool_call_id, {})
            tool_name = tool_call.get("name", "unknown_tool")
            args_summary = _summarize_tool_args(tool_call.get("args", {}))
            observation = _truncate_text(
                _stringify_content(message.content),
                limit=MAX_TOOL_OBSERVATION_CHARS,
            )
            parts.append(
                "\n".join(
                    [
                        "tool_observation",
                        f"tool_name: {tool_name}",
                        f"tool_call_id: {message.tool_call_id}",
                        f"args: {args_summary}",
                        "result:",
                        observation,
                    ]
                )
            )
            continue

        if isinstance(message, SystemMessage):
            parts.append(
                f"system\n{_truncate_text(_stringify_content(message.content), limit=MAX_MESSAGE_CONTENT_CHARS)}"
            )

    return "\n\n---\n\n".join(parts)


async def compress_context(
    history: list[BaseMessage],
    settings: Settings | None = None,
) -> CompressionSummary:
    settings = settings or get_settings()
    history_text = render_history_for_compression(history)

    model = create_model(settings)
    compressed = await model.ainvoke(
        [
            SystemMessage(content=COMPRESS_SYSTEM),
            HumanMessage(content=history_text),
        ]
    )

    return CompressionSummary.from_text(compressed.content)


def build_compressed_context(summary: CompressionSummary) -> str:
    return CONTEXT_TEMPLATE.format(
        completed=summary.completed or "None",
        remaining=summary.remaining or "None",
        current_state=summary.current_state or "None",
        notes=summary.notes or "None",
    )
