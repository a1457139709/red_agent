from __future__ import annotations

from collections.abc import Iterable

from langchain.tools import BaseTool

from .contracts import SecurityTool


def register_tool(tool: BaseTool):
    """
    Compatibility shim for the legacy tool declaration style.
    The project now assembles tools explicitly in tools/__init__.py,
    so this decorator only passes the tool object through unchanged.
    """
    return tool


def build_legacy_registry(
    tools: Iterable[BaseTool],
    allowed_names: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, BaseTool]:
    allowed = None if allowed_names is None else set(allowed_names)
    return {
        tool.name: tool
        for tool in tools
        if allowed is None or tool.name in allowed
    }


def build_security_registry(
    tools: Iterable[SecurityTool],
    allowed_names: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, SecurityTool]:
    allowed = None if allowed_names is None else set(allowed_names)
    return {
        tool.name: tool
        for tool in tools
        if allowed is None or tool.name in allowed
    }
