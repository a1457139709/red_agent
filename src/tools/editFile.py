from pathlib import *
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
        "old_string": {
            "type": "string",
            "description":"要被替换的旧字符串，要求在文件中唯一存在（仅出现一次），否则会报错"
        },
        "new_string": {
            "type": "string",
            "description":"替换后的新字符串"
        }
    },
    "required": ["file_path", "old_string", "new_string"]
}

@register_tool
@tool("edit_file", description="替换文件中的特定字符串。old_string 必须在文件中唯一存在（仅出现一次），否则会报错。建议先用 read_file 确认目标字符串。",args_schema=tool_schema)
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    # 路径安全检查
    try:
        safe_path = resolve_safe_path(file_path)
    except ValueError as e:
        return f"{str(e)}"
    
    # 替换文件内容
    if not safe_path.exists():
        return f"Error：文件不存在 - {safe_path.as_posix()}"
    
    if not safe_path.is_file():
        return f"Error：编辑的是目录而不是文件 - {safe_path.as_posix()}"
    
    try:
        old_content = safe_path.read_text(encoding="utf-8")

        # 唯一性校验：old_string 必须恰好出现 1 次
        # 不唯一的替换会产生难以追踪的错误，所以这里严格校验
        occurrences = old_content.count(old_string)
        if occurrences == 0:
            return "Error：未找到要替换的字符串"
        elif occurrences > 1:
            return f"Error：要替换的字符串出现了 {occurrences} 次，无法确定替换位置，请修改 old_string 使其唯一"
        
        new_content = old_content.replace(old_string, new_string)

        if new_content == old_content:
            return "Error：替换后内容与原内容相同，未进行任何修改"

        safe_path.write_text(new_content, encoding="utf-8")

        return f"文件编辑成功, 路径：{safe_path.as_posix()}"
    except Exception as e:
        return f"Error：文件编辑失败 - {str(e)}" 
