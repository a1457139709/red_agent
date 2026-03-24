from pathlib import *
from langchain.tools import tool
from .registry import register_tool
from utils.safety import resolve_safe_path

tool_schema = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description":"要搜索的内容"
        },
        "file_path": {
            "type": "string",
            "description":"文件路径（相对于当前工作目录）"
        }
    },
    "required": ["query", "file_path"]
}

@register_tool
@tool("search", description="在文件中搜索内容，返回存在要搜索的内容的完整行",args_schema=tool_schema)
def search(query: str, file_path: str = "."):
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return str(e)

    results = []

    if not safe_path.exists():
        return f"Error: 路径 {file_path} 不存在"

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
                        results.append(
                            f"{f}:{i} {line.strip()}"
                        )

                        if len(results) > 30:
                            return "\n".join(results)

        except:
            pass

    return "\n".join(results)
