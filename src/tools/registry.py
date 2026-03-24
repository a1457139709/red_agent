from langchain.tools import BaseTool

def register_tool(tool: BaseTool):
    """
    兼容旧的工具定义方式。
    当前项目改为在 tools/__init__.py 中显式装配工具，装饰器仅做透传。
    """
    return tool
