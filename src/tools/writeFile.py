from pathlib import *

from langchain.tools import tool

from utils.safety import resolve_safe_path

from .registry import register_tool


tool_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "File path relative to the current working directory",
        },
        "content": {
            "type": "string",
            "description": "Content to write",
        },
    },
    "required": ["file_path", "content"],
}


@register_tool
@tool(
    "write_file",
    description=(
        "Write content to a file. Create the file if it does not exist, otherwise "
        "overwrite it completely. Use edit_file for targeted edits."
    ),
    args_schema=tool_schema,
)
def write_file(file_path: str, content: str) -> str:
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"

    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"Error: failed to write file - {str(e)}"

    return f"File written successfully: {safe_path.as_posix()} ({len(content)} characters)"