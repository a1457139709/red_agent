from langchain.tools import tool

from utils.safety import resolve_safe_path

from .registry import register_tool


tool_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Directory path to list",
        }
    },
    "required": ["path"],
}


@register_tool
@tool(
    "list_dir",
    description="List files and directories in the target folder without recursion.",
    args_schema=tool_schema,
)
def list_dir(path: str = ".") -> str:
    """List directory contents."""

    try:
        dir_path = resolve_safe_path(path)
    except ValueError as e:
        return str(e)

    if not dir_path.exists():
        return f"Error: path does not exist - {path}"

    if not dir_path.is_dir():
        return f"Error: path is not a directory - {path}"

    entries = []

    for p in sorted(dir_path.iterdir()):
        if p.is_dir():
            entries.append(f"[DIR]  {p.name}")
        else:
            entries.append(f"[FILE] {p.name}")

    return "\n".join(entries)