from .bash import execute_command
from .deleteFile import delete_file
from .editFile import edit_file
from .listDir import list_dir
from .readFile import read_file
from .search import search
from .writeFile import write_file

AVAILABLE_TOOLS = [
    execute_command,
    delete_file,
    edit_file,
    list_dir,
    read_file,
    search,
    write_file,
]


def get_tools():
    return list(AVAILABLE_TOOLS)


def build_tool_registry():
    return {tool.name: tool for tool in AVAILABLE_TOOLS}
