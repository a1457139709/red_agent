from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage


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
