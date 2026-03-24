from utils.safety import resolve_safe_path
from pathlib import *
from utils.truncate import truncate_tool_output
from langchain.tools import tool
from .registry import register_tool
tool_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description":"文件路径（相对于当前工作目录）"
        },
        "offset": {
            "type": "int",
            "description":"从第几行开始读（0-indexed，默认从头）"
        },
        "limit": {
            "type": "int",
            "description":"最多读取多少行（默认读到文件末尾）"
        },
    },
    "required": ["file_path"]
}

@register_tool
@tool("read_file", description="读取本地文件内容。大文件建议用 offset + limit 分段读取，避免一次性读取撑爆上下文。输出带行号，方便定位。",args_schema=tool_schema)
def read_file(file_path: str, offset: int=None, limit: int=None) -> str:
    # 路径安全检查
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"
    
    # 文件读取，按照 offset 和 limit 截取内容， offset 和 limit 以行为单位

    if not safe_path.exists():
        return f"Error：文件不存在 - {safe_path.as_posix()}"
    
    if not safe_path.is_file():
        return f"Error：读取的是目录而不是文件 - {safe_path.as_posix()}"
    
    try:
        with safe_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

            start = offset if offset else 0
            end = start + limit if limit else len(lines)

            if start >= len(lines):
                return f"Error：offset 超出文件总行数 - {len(lines)}行"
            slices = lines[start:end]
    except Exception:
        slices = []
        return f"Error：文件读取失败"
    
    # 添加行号，方便LLM定位
    with_line_numbers = "\n".join(
        f"{start + i + 1}\t{line}"
        for i, line in enumerate(slices)
    )

    # 添加元数据，告诉LLM读取了多少

    metadata = f"<system_hint type=\"file_read\" path=\"{safe_path.as_posix()}\", offset=\"{start}\", limit=\"{limit}\"," + \
                f"actual_lines=\"{len(slices)}\", file_total_lines=\"{len(lines)}\" />\n"

    return truncate_tool_output("read_file", metadata + with_line_numbers)
