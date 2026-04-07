from langchain.tools import BaseTool

from .bash import execute_command
from .contracts import SecurityTool
from .deleteFile import delete_file
from .editFile import edit_file
from .listDir import list_dir
from .readFile import read_file
from .registry import build_legacy_registry, build_security_registry
from .search import search
from .security import AVAILABLE_SECURITY_TOOLS
from .webFetch import web_fetch
from .webSearch import web_search
from .writeFile import write_file

AVAILABLE_TOOLS = [
    execute_command,
    delete_file,
    edit_file,
    list_dir,
    read_file,
    search,
    web_fetch,
    web_search,
    write_file,
]


def get_tools() -> list[BaseTool]:
    return list(AVAILABLE_TOOLS)


def get_security_tools() -> list[SecurityTool]:
    return list(AVAILABLE_SECURITY_TOOLS)


def build_tool_registry(allowed_names: list[str] | set[str] | tuple[str, ...] | None = None):
    return build_legacy_tool_registry(allowed_names)


def build_legacy_tool_registry(allowed_names: list[str] | set[str] | tuple[str, ...] | None = None):
    return build_legacy_registry(AVAILABLE_TOOLS, allowed_names)


def build_security_tool_registry(
    allowed_names: list[str] | set[str] | tuple[str, ...] | None = None,
):
    return build_security_registry(AVAILABLE_SECURITY_TOOLS, allowed_names)
