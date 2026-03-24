from utils.safety import resolve_safe_path

from pathlib import *
from langchain.tools import tool
from .registry import register_tool
tool_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description":"文件路径（相对于当前工作目录）"
        },
        "content": {
            "type": "string",
            "description":"要写入的内容"
        }
    },
    "required": ["file_path", "content"]
}

@register_tool
@tool("write_file", description="将内容写入文件。文件不存在则创建，已存在则完整覆盖。局部修改请用 edit_file，避免不必要的全量重写",args_schema=tool_schema)
def write_file(file_path: str, content: str) -> str:
    # 路径安全检查
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"
    
    # 文件写入

    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在
        # with safe_path.open("w", encoding="utf-8") as f:
        #     f.write(content)
        safe_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"Error：文件写入失败 - {str(e)}"
    
    return f"文件写入成功，路径：{safe_path.as_posix()}，已写入 {len(content)} 字符"
