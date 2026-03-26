from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage


def _serialize_message(message: BaseMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": message.content,
        "additional_kwargs": dict(message.additional_kwargs),
    }

    if isinstance(message, HumanMessage):
        payload["type"] = "human"
    elif isinstance(message, AIMessage):
        payload["type"] = "ai"
        payload["tool_calls"] = list(message.tool_calls)
        usage_metadata = getattr(message, "usage_metadata", None)
        if usage_metadata:
            payload["usage_metadata"] = dict(usage_metadata)
    elif isinstance(message, ToolMessage):
        payload["type"] = "tool"
        payload["tool_call_id"] = message.tool_call_id
    elif isinstance(message, SystemMessage):
        payload["type"] = "system"
    else:
        raise TypeError(f"Unsupported message type for checkpointing: {type(message)!r}")

    return payload


def _deserialize_message(payload: dict[str, Any]) -> BaseMessage:
    message_type = payload["type"]
    common_kwargs = {
        "content": payload.get("content"),
        "additional_kwargs": payload.get("additional_kwargs") or {},
    }

    if message_type == "human":
        return HumanMessage(**common_kwargs)
    if message_type == "ai":
        return AIMessage(
            **common_kwargs,
            tool_calls=payload.get("tool_calls") or [],
            usage_metadata=payload.get("usage_metadata"),
        )
    if message_type == "tool":
        return ToolMessage(
            **common_kwargs,
            tool_call_id=payload["tool_call_id"],
        )
    if message_type == "system":
        return SystemMessage(**common_kwargs)
    raise ValueError(f"Unsupported checkpoint message type: {message_type}")


@dataclass
class SessionState:
    history: list[BaseMessage] = field(default_factory=list)
    compressed_summary: str | None = None
    last_usage: dict[str, Any] = field(default_factory=dict)

    @property
    def context_summary(self) -> str:
        return self.compressed_summary or ""

    def reset(self) -> None:
        self.history.clear()
        self.compressed_summary = None
        self.last_usage = {}

    def append_user_message(self, question: str) -> None:
        self.history.append(HumanMessage(content=question))

    def append_messages(self, messages: list[BaseMessage]) -> None:
        self.history.extend(messages)

    def set_usage(self, usage: dict[str, Any] | None) -> None:
        self.last_usage = usage or {}

    def apply_compressed_summary(self, summary: str) -> None:
        self.history.clear()
        self.compressed_summary = summary

    def to_checkpoint_payload(self) -> dict[str, Any]:
        return {
            "history": [_serialize_message(message) for message in self.history],
            "compressed_summary": self.compressed_summary,
            "last_usage": dict(self.last_usage),
        }

    @classmethod
    def from_checkpoint_payload(cls, payload: dict[str, Any]) -> "SessionState":
        history = [_deserialize_message(message) for message in payload.get("history", [])]
        return cls(
            history=history,
            compressed_summary=payload.get("compressed_summary"),
            last_usage=payload.get("last_usage") or {},
        )
