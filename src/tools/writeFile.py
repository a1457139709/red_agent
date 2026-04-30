from pathlib import *

from utils.safety import resolve_safe_path

from .registry import invokable


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


@invokable
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
