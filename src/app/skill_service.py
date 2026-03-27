from __future__ import annotations

from dataclasses import dataclass

from agent.prompt import assemble_system_prompt
from models.skill import LoadedSkill
from skills.registry import SkillRegistry


DEFAULT_SKILL_NAME = "development-default"


@dataclass(slots=True)
class SkillRuntimeConfig:
    skill: LoadedSkill
    system_prompt: str
    allowed_tools: list[str]


class SkillService:
    def __init__(self, registry: SkillRegistry, *, default_skill_name: str = DEFAULT_SKILL_NAME) -> None:
        self.registry = registry
        self.default_skill_name = default_skill_name

    def list_skills(self) -> list[LoadedSkill]:
        return self.registry.list_skills()

    def get_skill(self, name: str) -> LoadedSkill | None:
        return self.registry.get_skill(name)

    def resolve_skill(self, skill_name: str | None) -> LoadedSkill:
        return self.registry.require_skill(skill_name or self.default_skill_name)

    async def build_runtime_config(
        self,
        *,
        skill_name: str | None,
        context_summary: str,
    ) -> SkillRuntimeConfig:
        skill = self.resolve_skill(skill_name)
        system_prompt = await assemble_system_prompt(
            skill_prompt=skill.manifest.body,
            context_prompt=context_summary,
        )
        return SkillRuntimeConfig(
            skill=skill,
            system_prompt=system_prompt,
            allowed_tools=list(skill.manifest.allowed_tools),
        )
