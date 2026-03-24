from utils.safety import resolve_safe_path
from langchain.tools import tool
from .registry import register_tool
tool_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description":"文件路径（相对于当前工作目录）"
        },
    },
    "required": ["file_path"]
}

@register_tool
@tool("delete_file", description="删除指定的文件。",args_schema=tool_schema)
def delete_file(file_path: str) -> str:
    # 路径安全检查
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"
    
    # 文件删除
    if not safe_path.exists():
        return f"Error：文件不存在 - {safe_path.as_posix()}"
    
    if not safe_path.is_file():
        return f"Error：删除的不是一个文件 - {safe_path.as_posix()}"
    
    try:
        safe_path.unlink()
        return f"文件删除成功，路径：{safe_path.as_posix()}"
    except Exception as e:
        return f"Error：文件删除失败 - {str(e)}"
