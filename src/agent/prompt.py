from pathlib import Path

PROMPT_FILE = Path(__file__).parent.parent / "SYSTEM_PROMPT.md"
SKILL_PREFIX = "---\n# Skill Instructions\n\n"
CONTEXT_PREFIX = "---\n# Context Summary\n\n"


async def assemble_system_prompt(
    extra_prompt: str = "",
    *,
    skill_prompt: str = "",
    context_prompt: str = "",
) -> str:
    if extra_prompt:
        context_prompt = context_prompt or extra_prompt

    prompt = PROMPT_FILE.read_text(encoding="utf-8")

    if skill_prompt:
        prompt += "\n\n" + SKILL_PREFIX + skill_prompt.strip() + "\n"

    if context_prompt:
        prompt += "\n" + CONTEXT_PREFIX + context_prompt.strip() + "\n"

    return prompt
