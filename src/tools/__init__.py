from .bash import execute_command
from .deleteFile import delete_file
from .editFile import edit_file
from .listDir import list_dir
from .readFile import read_file
from .search import search
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


def get_tools():
    return list(AVAILABLE_TOOLS)


def build_tool_registry(allowed_names: list[str] | set[str] | tuple[str, ...] | None = None):
    allowed = None if allowed_names is None else set(allowed_names)
    return {
        tool.name: tool
        for tool in AVAILABLE_TOOLS
        if allowed is None or tool.name in allowed
    }
