from __future__ import annotations

from dataclasses import dataclass

from agent.prompt import assemble_system_prompt
from models.skill import LoadedSkill
from skills.registry import SkillRegistry
from tools.policy import RuntimeSafetyPolicy


DEFAULT_SKILL_NAME = "development-default"


@dataclass(slots=True)
class SkillRuntimeConfig:
    skill: LoadedSkill | None
    system_prompt: str
    allowed_tools: list[str]
    safety_policy: RuntimeSafetyPolicy


class SkillService:
    def __init__(
        self,
        registry: SkillRegistry,
        *,
        base_tool_names: list[str] | None = None,
        default_skill_name: str = DEFAULT_SKILL_NAME,
        default_task_skill_name: str | None = DEFAULT_SKILL_NAME,
    ) -> None:
        self.registry = registry
        self.base_tool_names = list(base_tool_names or sorted(registry.known_tool_names))
        self.default_skill_name = default_skill_name
        self.default_task_skill_name = default_task_skill_name
        self.base_safety_policy = RuntimeSafetyPolicy.for_tool_names(self.base_tool_names)

    def list_skills(self) -> list[LoadedSkill]:
        return self.registry.list_skills()

    def get_skill(self, name: str) -> LoadedSkill | None:
        return self.registry.get_skill(name)

    def reload(self) -> None:
        self.registry.reload()

    def require_skill(self, name: str) -> LoadedSkill:
        return self.registry.require_skill(name)

    def resolve_skill(self, skill_name: str | None) -> LoadedSkill:
        resolved_name = skill_name or self.default_skill_name
        if not resolved_name:
            raise ValueError("Skill name is required")
        return self.registry.require_skill(resolved_name)

    async def build_base_runtime_config(
        self,
        *,
        context_summary: str,
    ) -> SkillRuntimeConfig:
        system_prompt = await assemble_system_prompt(
            context_prompt=context_summary,
        )
        return SkillRuntimeConfig(
            skill=None,
            system_prompt=system_prompt,
            allowed_tools=list(self.base_tool_names),
            safety_policy=self.base_safety_policy,
        )

    async def build_skill_runtime_config(
        self,
        *,
        skill_name: str,
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
            safety_policy=RuntimeSafetyPolicy.for_tool_names(
                skill.manifest.allowed_tools,
                base_policy=self.base_safety_policy,
            ),
        )

    async def build_runtime_config(
        self,
        *,
        skill_name: str | None,
        context_summary: str,
    ) -> SkillRuntimeConfig:
        return await self.build_skill_runtime_config(
            skill_name=self.resolve_skill(skill_name).manifest.name,
            context_summary=context_summary,
        )
