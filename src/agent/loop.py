from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .logger import log_step
from .prompt import assemble_system_prompt
from .provider import create_model
from .settings import DEFAULT_MAX_AGENT_STEPS, Settings, get_settings
from .state import SessionState
from tools.executor import ToolExecutor


MAX_AGENT_STEPS = DEFAULT_MAX_AGENT_STEPS


async def agent_loop(
    question: str,
    session_state: SessionState,
    tool_executor: ToolExecutor,
    settings: Settings | None = None,
    *,
    system_prompt: str | None = None,
    tools: list | None = None,
) -> dict:
    settings = settings or get_settings()
    if system_prompt is None:
        system_prompt = await assemble_system_prompt(session_state.context_summary)
    model_without_tools = create_model(settings)
    visible_tools = tools if tools is not None else tool_executor.get_tools()
    model = model_without_tools.bind_tools(visible_tools)

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(session_state.history)
    messages.append(HumanMessage(content=question))

    steps = []
    last_usage = None
    max_steps = settings.max_agent_steps

    for _ in range(max_steps):
        res = await model.ainvoke(messages)
        ai_message: AIMessage = res
        last_usage = ai_message.usage_metadata
        tool_calls = ai_message.tool_calls

        if not tool_calls:
            return {
                "status": "completed",
                "response": res.content,
                "messages": steps + [res],
                "usage": ai_message.usage_metadata,
            }

        log_step(ai_message, tool_calls)
        messages.append(ai_message)
        steps.append(ai_message)

        for tool_call in tool_calls:
            tool_result = tool_executor.execute(tool_call["name"], tool_call["args"])
            tool_message = ToolMessage(
                content=tool_result,
                tool_call_id=tool_call["id"],
            )
            messages.append(tool_message)
            steps.append(tool_message)

    return {
        "status": "max_steps_exceeded",
        "response": (
            f"Task did not complete within {max_steps} steps. "
            f"任务在 {max_steps} 步内仍未完成，请缩小问题范围或继续追问。"
        ),
        "messages": steps,
        "usage": last_usage or {},
    }
