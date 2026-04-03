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
        "old_string": {
            "type": "string",
            "description": "Existing string to replace; it must appear exactly once in the file",
        },
        "new_string": {
            "type": "string",
            "description": "Replacement string",
        },
    },
    "required": ["file_path", "old_string", "new_string"],
}


@register_tool
@tool(
    "edit_file",
    description=(
        "Replace a specific string in a file. old_string must appear exactly once, "
        "or the edit is rejected. Use read_file first to confirm the target text."
    ),
    args_schema=tool_schema,
)
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"

    if not safe_path.exists():
        return f"Error: file does not exist - {safe_path.as_posix()}"

    if not safe_path.is_file():
        return f"Error: target is a directory, not a file - {safe_path.as_posix()}"

    try:
        old_content = safe_path.read_text(encoding="utf-8")

        occurrences = old_content.count(old_string)
        if occurrences == 0:
            return "Error: target string was not found"
        if occurrences > 1:
            return (
                "Error: target string appears "
                f"{occurrences} times, so the replacement location is ambiguous. "
                "Please make old_string unique."
            )

        new_content = old_content.replace(old_string, new_string)

        if new_content == old_content:
            return "Error: replacement produced no file changes"

        safe_path.write_text(new_content, encoding="utf-8")

        return f"File edited successfully: {safe_path.as_posix()}"
    except Exception as e:
        return f"Error: failed to edit file - {str(e)}"