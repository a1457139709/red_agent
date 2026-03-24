from .provider import create_model
from .prompt import assemble_system_prompt
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from .settings import DEFAULT_MAX_AGENT_STEPS, Settings, get_settings
from .state import SessionState
from .logger import log_step
from tools.executor import ToolExecutor

MAX_AGENT_STEPS = DEFAULT_MAX_AGENT_STEPS
# Agent 执行循环
# 1. 构建系统提示词，如果有上下文压缩摘要，也在这里拼装进去
# 2. 构建 Agent 实例，注册工具
# 3. 调用 Agent 执行，打印中间过程
# 返回 Agent 输出，token使用，中间步骤和中间步骤数不好获得，后续可以通过 langchain 的 callback 来收集
async def agent_loop(
        question: str,
        session_state: SessionState,
        tool_executor: ToolExecutor,
        settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    # 构建系统提示词
    system_prompt = await assemble_system_prompt(session_state.context_summary)

    # 构建 Agent 实例
    model_without_tools = create_model(settings)
    tools = tool_executor.get_tools()
    # print(tools)
    # agent = create_agent(
    #     model=model,
    #     tools=tools,
    #     system_prompt=SystemMessage(content=system_prompt),
        
    # )
    model = model_without_tools.bind_tools(tools)
    # 调用 Agent 执行
    messages = []
    messages.append(SystemMessage(content=system_prompt))
    messages.extend(session_state.history)
    messages.append(HumanMessage(content=question))
    
    # res = agent.invoke(
    #     {"messages": messages}
    # )
    steps = []
    last_usage = None
    max_steps = settings.max_agent_steps
    for _ in range(max_steps):
        res = await model.ainvoke(
            messages
        )
        #AI_message = res["messages"][-1]
        AI_message = res
        last_usage = AI_message.usage_metadata
        
        tool_calls = AI_message.tool_calls

        
        # 如果没有工具调用，说明 Agent 完成了任务，返回其结果
        if not tool_calls:
            return {
            "status": "completed",
            "response": res.content,
            "messages": steps + [res],
            "usage": AI_message.usage_metadata,
        }
        log_step(AI_message, tool_calls)
        messages.append(AI_message)
        steps.append(AI_message)
        # 否则，执行工具调用，并将结果作为 ToolMessage 追加到 messages 中，继续下一轮循环
        for tool_call in AI_message.tool_calls:
            # print(f"[*] Tool: {tool_call['name']}, Args: {tool_call['args']}")
            tool_result = tool_executor.execute(tool_call["name"], tool_call["args"])
             
            tool_message =ToolMessage(
                content=tool_result,
                tool_call_id = tool_call["id"]
            )
            
            messages.append(tool_message)
            steps.append(tool_message)

    return {
        "status": "max_steps_exceeded",
        "response": f"任务在 {max_steps} 步内仍未完成，请缩小问题范围或继续追问。",
        "messages": steps,
        "usage": last_usage or {},
    }
