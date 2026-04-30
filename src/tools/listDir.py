from utils.safety import resolve_safe_path

from .registry import invokable


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


@invokable
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
