from pathlib import Path

PROMPT_FILE = Path(__file__).parent.parent / "SYSTEM_PROMPT.md"
FORMAT_PREFIX = "---\n# 额外提示\n\n"

# 系统提示词分三段拼装：
#   Segment 1: 静态核心指令（SYSTEM_PROMPT.md）,工具使用补充说明
#   Segment 3: 运行时状态（可选，如上下文压缩摘要）
async def assemble_system_prompt(extra_prompt: str) -> str:
    prompt = ""

    # 读取系统提示词

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    prompt += system_prompt

    # 拼装额外提示词

    if extra_prompt:
        prompt += FORMAT_PREFIX + extra_prompt + "\n\n"

    return prompt