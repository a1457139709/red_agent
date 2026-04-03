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
    },
    "required": ["file_path"],
}


@register_tool
@tool("delete_file", description="Delete the specified file.", args_schema=tool_schema)
def delete_file(file_path: str) -> str:
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"

    if not safe_path.exists():
        return f"Error: file does not exist - {safe_path.as_posix()}"

    if not safe_path.is_file():
        return f"Error: target is not a file - {safe_path.as_posix()}"

    try:
        safe_path.unlink()
        return f"File deleted successfully: {safe_path.as_posix()}"
    except Exception as e:
        return f"Error: failed to delete file - {str(e)}"