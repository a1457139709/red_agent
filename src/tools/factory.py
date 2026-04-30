from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Union

from langchain.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from tools.policy import CapabilityTier


ToolCallable = Callable[..., Union[str, "ToolResultEnvelope"]]


@dataclass(frozen=True, slots=True)
class ToolPresentation:
    title: str | None = None
    group: str | None = None
    accent: str = "cyan"

    def to_payload(self) -> dict[str, str]:
        payload = {"accent": self.accent}
        if self.title:
            payload["title"] = self.title
        if self.group:
            payload["group"] = self.group
        return payload


@dataclass(frozen=True, slots=True)
class ToolResultEnvelope:
    summary: str
    model_text: str
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    presentation: ToolPresentation = field(default_factory=ToolPresentation)

    def to_model_text(self) -> str:
        return self.model_text

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "model_text": self.model_text,
            "data": dict(self.data),
            "artifacts": list(self.artifacts),
            "findings": list(self.findings),
            "presentation": self.presentation.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolCallable
    capability: CapabilityTier
    aliases: tuple[str, ...] = ()
    is_concurrency_safe: bool = False
    is_read_only: bool = False
    is_destructive: bool = False
    max_result_size_chars: int | None = 30_000
    presentation: ToolPresentation = field(default_factory=ToolPresentation)

    def run(self, arguments: dict[str, Any]) -> ToolResultEnvelope:
        parsed = self.input_model.model_validate(arguments)
        result = self.handler(**parsed.model_dump())
        if isinstance(result, ToolResultEnvelope):
            return result
        return text_result_envelope(
            text=str(result),
            presentation=self.presentation,
        )

    def build_langchain_tool(self) -> BaseTool:
        def invoke_with_validation(**kwargs: Any) -> str:
            return self.run(kwargs).to_model_text()

        invoke_with_validation.__name__ = self.name
        return StructuredTool.from_function(
            func=invoke_with_validation,
            name=self.name,
            description=self.description,
            args_schema=self.input_model,
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "capability": self.capability.value,
            "is_concurrency_safe": self.is_concurrency_safe,
            "is_read_only": self.is_read_only,
            "is_destructive": self.is_destructive,
            "max_result_size_chars": self.max_result_size_chars,
            "presentation": self.presentation.to_payload(),
            "input_schema": self.input_model.model_json_schema(),
        }


def build_tool(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
    handler: ToolCallable,
    capability: CapabilityTier,
    aliases: tuple[str, ...] = (),
    is_concurrency_safe: bool = False,
    is_read_only: bool = False,
    is_destructive: bool = False,
    max_result_size_chars: int | None = 30_000,
    presentation: ToolPresentation | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_model=input_model,
        handler=handler,
        capability=capability,
        aliases=aliases,
        is_concurrency_safe=is_concurrency_safe,
        is_read_only=is_read_only,
        is_destructive=is_destructive,
        max_result_size_chars=max_result_size_chars,
        presentation=presentation or ToolPresentation(title=name),
    )


def text_result_envelope(
    *,
    text: str,
    presentation: ToolPresentation,
    data: dict[str, Any] | None = None,
) -> ToolResultEnvelope:
    first_line = text.splitlines()[0] if text else ""
    return ToolResultEnvelope(
        summary=first_line or text,
        model_text=text,
        data=dict(data or {}),
        presentation=presentation,
    )


def build_tool_registry_from_definitions(
    definitions: list[ToolDefinition] | tuple[ToolDefinition, ...],
    allowed_names: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, ToolDefinition]:
    allowed = None if allowed_names is None else set(allowed_names)
    registry: dict[str, ToolDefinition] = {}
    for definition in definitions:
        if allowed is not None and definition.name not in allowed:
            continue
        registry[definition.name] = definition
    return registry
