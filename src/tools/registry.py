from langchain.tools import BaseTool


def register_tool(tool: BaseTool):
    """
    Compatibility shim for the legacy tool declaration style.
    The project now assembles tools explicitly in tools/__init__.py,
    so this decorator only passes the tool object through unchanged.
    """
    return tool