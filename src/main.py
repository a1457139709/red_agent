from agent.loop import agent_loop
from agent.context import should_compress, compress_context, build_compressed_context
from agent.settings import get_settings
from agent.state import SessionState
import asyncio
from tools import build_tool_registry, get_tools
from tools.executor import ToolExecutor
from agent.logger import reset_steps, ColoredOutput
from utils.confirm import confirm_from_user
def print_help():
    tools = get_tools()
    print(
        f"""
        mini-claude-code — 教学用 Code Agent

        可用命令：
        /reset   清空当前会话历史
        /exit    退出
        /help    显示帮助

        可用工具：
        {tools}
        """
    )

async def main():
    settings = get_settings()
    session_state = SessionState()
    tool_executor = ToolExecutor(
        build_tool_registry(),
        confirm_command=confirm_from_user,
        on_info=ColoredOutput.print_info,
    )
    while True:
        try:
            question = input("\n> ").strip()
        except EOFError:
            break

        # ── slash commands ─────────────────────────────

        if question in ("/exit", "/quit"):
            ColoredOutput.print_header("再见！")
            break

        if question == "/reset":
            session_state.reset()
            ColoredOutput.print_header("会话已重置")
            continue

        if question == "/help":
            print_help()
            continue

        if not question:
            continue
        reset_steps()
        # ── Agent Loop ─────────────────────────────────
        try:
            #print("\n正在思考...")
            result = await agent_loop(
                question,
                session_state,
                tool_executor,
                settings,
            )
            
            text = result["response"]
            usage = result.get("usage") or {}
            status = result.get("status", "completed")

            if status == "completed":
                ColoredOutput.print_final_answer(text)
            else:
                ColoredOutput.print_error(text)
            # print(usage)
            # 保存历史
            session_state.append_user_message(question)
            session_state.append_messages(result["messages"])
            session_state.set_usage(usage)
            # # 多步才打印标题
            # if step_count > 1:
            #     print("\n── 最终回答 ─────────────────────")
            # ── 上下文压缩检测 ─────────────────────────

            total_tokens = usage.get("total_tokens")
            if total_tokens is not None and should_compress(total_tokens, settings):
            #if True:
                ColoredOutput.print_info("上下文接近上限，正在压缩...")

                try:
                    summary = await compress_context(session_state.history, settings)

                    hint = build_compressed_context(summary)

                    session_state.apply_compressed_summary(hint)

                    ColoredOutput.print_success("上下文已压缩，下次对话继续")
                    # print(hint)
                except Exception as e:
                    ColoredOutput.print_error(str(e))

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":

    # result = agent_loop(
    #     question="列出自己拥有的tools",
    #     history=[]
    # )
    # print(result["AIMessage"].content)

    print(
        "mini-claude-code"
        "0.1.0 — 输入 /help 查看帮助"
    )
    asyncio.run(main())
