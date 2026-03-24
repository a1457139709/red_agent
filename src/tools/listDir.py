
from utils.safety import resolve_safe_path
from langchain.tools import tool
from .registry import register_tool

tool_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description":"文件目录路径"
        }
    },
    "required": ["path"]
}

@register_tool
@tool("list_dir", description="列出目标文件夹下的目录和文件，不会递归列出子目录",args_schema=tool_schema)
def list_dir(path: str = ".") -> str:
    """
    列出目录
    """

    try:
        dir_path = resolve_safe_path(path)
    except ValueError as e:
        return str(e)

    if not dir_path.exists():
        return f"Error: 路径 {path} 不存在"

    if not dir_path.is_dir():
        return f"Error: {path} 不是一个目录"

    entries = []

    for p in sorted(dir_path.iterdir()):
        if p.is_dir():
            entries.append(f"[DIR]  {p.name}")
        else:
            entries.append(f"[FILE] {p.name}")

    return "\n".join(entries)