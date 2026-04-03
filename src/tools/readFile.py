from pathlib import *

from langchain.tools import tool

from utils.safety import resolve_safe_path
from utils.truncate import truncate_tool_output

from .registry import register_tool


tool_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "File path relative to the current working directory",
        },
        "offset": {
            "type": "int",
            "description": "Zero-based starting line offset; defaults to the beginning",
        },
        "limit": {
            "type": "int",
            "description": "Maximum number of lines to read; defaults to the end of the file",
        },
    },
    "required": ["file_path"],
}


@register_tool
@tool(
    "read_file",
    description=(
        "Read a local file. For large files, prefer offset + limit to read in chunks. "
        "Output includes line numbers for easier navigation."
    ),
    args_schema=tool_schema,
)
def read_file(file_path: str, offset: int = None, limit: int = None) -> str:
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"

    if not safe_path.exists():
        return f"Error: file does not exist - {safe_path.as_posix()}"

    if not safe_path.is_file():
        return f"Error: target is a directory, not a file - {safe_path.as_posix()}"

    try:
        with safe_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

            start = offset if offset else 0
            end = start + limit if limit else len(lines)

            if start >= len(lines):
                return f"Error: offset exceeds total line count - {len(lines)} lines"
            slices = lines[start:end]
    except Exception:
        return "Error: failed to read file"

    with_line_numbers = "\n".join(
        f"{start + i + 1}\t{line}"
        for i, line in enumerate(slices)
    )

    metadata = (
        f"<system_hint type=\"file_read\" path=\"{safe_path.as_posix()}\", "
        f"offset=\"{start}\", limit=\"{limit}\","
        f"actual_lines=\"{len(slices)}\", file_total_lines=\"{len(lines)}\" />\n"
    )

    return truncate_tool_output("read_file", metadata + with_line_numbers)