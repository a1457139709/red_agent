from pathlib import *

from langchain.tools import tool

from utils.safety import resolve_safe_path

from .registry import register_tool


tool_schema = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Text to search for",
        },
        "file_path": {
            "type": "string",
            "description": "File or directory path relative to the current working directory",
        }
    },
    "required": ["query", "file_path"],
}


@register_tool
@tool(
    "search",
    description="Search file contents and return complete matching lines.",
    args_schema=tool_schema,
)
def search(query: str, file_path: str = "."):
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return str(e)

    results = []

    if not safe_path.exists():
        return f"Error: path does not exist - {file_path}"

    if safe_path.is_file():
        candidates = [safe_path]
    else:
        candidates = safe_path.rglob("*")

    for f in candidates:
        if not f.is_file():
            continue

        try:
            with f.open(errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
                    if query in line:
                        results.append(f"{f}:{i} {line.strip()}")

                        if len(results) > 30:
                            return "\n".join(results)
        except Exception:
            pass

    return "\n".join(results)