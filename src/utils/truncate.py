MAX_TOOL_OUTPUT = 8000

def truncate_tool_output(toolName: str,output: str) -> str:
    """
    Truncate the tool output to fit within the maximum allowed length.
    
    Args:
        output (str): The original tool output.
        
    Returns:
        str: The truncated tool output if it exceeds the maximum length, otherwise the original output.
    """

    
    if len(output) < MAX_TOOL_OUTPUT:
        return output
    
    formatted_output =  f'''
    <system_hint type="tool_output_omitted" tool="${toolName}" reason="too_long"
        actual_chars="${len(output)}" max_chars="${MAX_TOOL_OUTPUT}">
        工具输出过长，已自动截断。如需完整内容，请用 offset/limit 参数分段调用。
    </system_hint>
    '''
    limited_output = output[:MAX_TOOL_OUTPUT]
    return limited_output + formatted_output