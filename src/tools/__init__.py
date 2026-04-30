from .contracts import SecurityTool
from .definitions import BASE_TOOL_DEFINITIONS, RUNTIME_TOOL_DEFINITIONS
from .factory import ToolDefinition, build_tool_registry_from_definitions
from .registry import build_security_registry
from .security import AVAILABLE_SECURITY_TOOLS


def get_tool_definitions() -> list[ToolDefinition]:
    return list(BASE_TOOL_DEFINITIONS)


def get_runtime_tool_definitions() -> list[ToolDefinition]:
    return list(RUNTIME_TOOL_DEFINITIONS)


def get_tools():
    return [definition.build_langchain_tool() for definition in BASE_TOOL_DEFINITIONS]


def get_runtime_tools():
    return [definition.build_langchain_tool() for definition in RUNTIME_TOOL_DEFINITIONS]


def get_security_tools() -> list[SecurityTool]:
    return list(AVAILABLE_SECURITY_TOOLS)


def build_tool_registry(allowed_names: list[str] | set[str] | tuple[str, ...] | None = None):
    return build_runtime_registry(allowed_names)


def build_runtime_registry(allowed_names: list[str] | set[str] | tuple[str, ...] | None = None):
    return build_tool_registry_from_definitions(RUNTIME_TOOL_DEFINITIONS, allowed_names)


def build_legacy_tool_registry(allowed_names: list[str] | set[str] | tuple[str, ...] | None = None):
    return build_tool_registry_from_definitions(BASE_TOOL_DEFINITIONS, allowed_names)


def build_security_tool_registry(
    allowed_names: list[str] | set[str] | tuple[str, ...] | None = None,
):
    return build_security_registry(AVAILABLE_SECURITY_TOOLS, allowed_names)
