import json
import re
from dataclasses import dataclass

from .provider import create_model
from .settings import (
    DEFAULT_COMPRESSION_THRESHOLD,
    DEFAULT_CONTEXT_TOKEN_LIMIT,
    Settings,
    get_settings,
)
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
CHARS_PER_TOKEN = 3
MODEL_CONTEXT_TOKEN_LIMIT = DEFAULT_CONTEXT_TOKEN_LIMIT
COMPRESSION_THRESHOLD = DEFAULT_COMPRESSION_THRESHOLD


@dataclass
class CompressionSummary:
    completed: str = ""
    remaining: str = ""
    current_state: str = ""
    notes: str = ""

    @classmethod
    def from_text(cls, text: str) -> "CompressionSummary":
        def extract(tag: str) -> str:
            match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.DOTALL)
            return match.group(1).strip() if match else ""

        summary = cls(
            completed=extract("completed"),
            remaining=extract("remaining"),
            current_state=extract("current_state"),
            notes=extract("notes"),
        )

        if not any([summary.completed, summary.remaining, summary.current_state, summary.notes]):
            summary.notes = text.strip()

        return summary

def estimate_token(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN

def should_compress(current_tokens: int, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return current_tokens > settings.context_token_limit * settings.compression_threshold

async def compress_context(history: list, settings: Settings | None = None) -> CompressionSummary:
    settings = settings or get_settings()
    # 使用AI语言模型自动压缩，提炼已完成的任务，说明未完成的任务，当前状态，以及用户给出的注意事项。
    COMPRESS_SYSTEM = """
        你是一个 Agent 执行历史压缩器。将以下执行历史总结为结构化摘要，输出格式如下（使用 XML 标签）：

        <completed>
        已完成的具体操作（每行一条，保留关键细节）
        </completed>

        <remaining>
        还未完成的任务或子任务
        </remaining>

        <current_state>
        当前状态：已修改的文件路径、关键变量、环境状态等
        </current_state>

        <notes>
        注意事项：踩过的坑、特殊处理、边界条件
        </notes>

        要求：信息密度高，去掉废话，保留所有对后续执行有用的细节。
        """.strip()
    
    parts = []
    for message in history:
        if isinstance(message,HumanMessage):
            parts.append(f"user\n{message.content}")
        
        if isinstance(message,AIMessage):
            content = (message.content if isinstance(message.content, str) else json.dumps(message.content,ensure_ascii=False))
            parts.append(f"assistant\n{content}")

    history_text = "\n\n---\n\n".join(parts)

    # todo 调用 langchain 模型压缩, 
    """
    const { text } = await generateText({
    model,
    system: COMPRESS_SYSTEM,
    prompt: historyText,
    maxSteps: 1,
    })
    """
    model = create_model(settings)
    compressed = await model.ainvoke(
        [SystemMessage(content=COMPRESS_SYSTEM),
         HumanMessage(content=history_text)]
    )

    return CompressionSummary.from_text(compressed.content)

def build_compressed_context(summary: CompressionSummary)-> str:
    # 将压缩后的摘要重新格式化为 Agent 可理解的上下文
    CONTEXT_TEMPLATE = """
    以下是执行历史的压缩摘要：

    <completed>
    {completed}
    </completed>

    <remaining>
    {remaining}
    </remaining>

    <current_state>
    {current_state}
    </current_state>

    <notes>
    {notes}
    </notes>

    这是对 Agent 执行历史的总结，包含已完成的操作、未完成的任务、当前状态和注意事项。请基于此摘要继续执行后续任务。
    """.strip()

    return CONTEXT_TEMPLATE.format(
        completed=summary.completed or "无",
        remaining=summary.remaining or "无",
        current_state=summary.current_state or "无",
        notes=summary.notes or "无",
    )
