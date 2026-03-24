import subprocess
from utils.truncate import truncate_tool_output
from langchain.tools import tool
from .registry import register_tool

tool_schema = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description":"要执行的 Shell 命令"
        },
    },
    "required": ["command"]
}

@register_tool
@tool("bash", description="执行 Shell 命令。危险命令（如 rm -rf）会暂停并等待用户确认。命令输出超长时自动截断。",args_schema=tool_schema)
def execute_command(command: str) -> str:
    """
    Executes a shell command and returns its output.
    
    Args:
        command (str): The shell command to execute.
    """
    # 命令执行
    try:
        result = subprocess.run(command, shell=True,text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # 整合输出
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
    except Exception as e:
        #print(f"Error executing command: {command}")
        #print(f"Error output: {e.stderr}")
        return "执行失败: " + str(e)

    parts = []
    if stdout:
        parts.append(f"[stdout]:\n{stdout}")
    if stderr:
        parts.append(f"[stderr]:\n{stderr}")
    output = "\n".join(parts)
    return truncate_tool_output("bash",output)
