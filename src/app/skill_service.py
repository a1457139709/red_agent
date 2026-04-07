from __future__ import annotations

from dataclasses import dataclass, replace

from agent.prompt import assemble_system_prompt
from agent.settings import Settings
from models.skill import LoadedSkill
from skills.registry import SkillRegistry
from tools.policy import RuntimeSafetyPolicy


DEFAULT_SKILL_NAME = "development-default"
SUPPORTED_DIRECT_SHELLS = {"powershell", "pwsh"}


@dataclass(slots=True)
class SkillRuntimeConfig:
    skill: LoadedSkill | None
    system_prompt: str
    allowed_tools: list[str]
    safety_policy: RuntimeSafetyPolicy
    model_name: str | None = None
    reasoning_effort: str | None = None
    preferred_shell: str | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    workflow_profile: str | None = None

    def with_settings(self, settings: Settings) -> Settings:
        updates: dict[str, object] = {}
        if self.model_name:
            updates["openai_model"] = self.model_name
        if self.reasoning_effort != settings.openai_reasoning_effort:
            updates["openai_reasoning_effort"] = self.reasoning_effort
        if not updates:
            return settings
        return replace(settings, **updates)


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

    def is_user_invocable(self, skill: LoadedSkill) -> bool:
        return skill.manifest.is_user_invocable

    def is_model_invocable(self, skill: LoadedSkill) -> bool:
        return skill.manifest.allows_model_invocation

    def require_user_invocable_skill(self, name: str) -> LoadedSkill:
        skill = self.resolve_skill(name)
        if not self.is_user_invocable(skill):
            raise ValueError(f"Skill '{skill.manifest.name}' is not user-invocable.")
        return skill

    def require_direct_prompt_skill(self, name: str) -> LoadedSkill:
        skill = self.require_user_invocable_skill(name)
        self.ensure_direct_prompt_allowed(skill)
        return skill

    def ensure_direct_prompt_allowed(self, skill: LoadedSkill) -> None:
        if not self.is_model_invocable(skill):
            if skill.manifest.workflow_profile:
                raise ValueError(
                    f"Skill '{skill.manifest.name}' disables direct model invocation. "
                    f"Use /skill plan {skill.manifest.name} <operation_id> or "
                    f"/skill apply {skill.manifest.name} <operation_id>."
                )
            raise ValueError(f"Skill '{skill.manifest.name}' disables direct model invocation.")
        normalized_shell = self._normalize_shell(skill.manifest.shell)
        if normalized_shell is None:
            return
        if normalized_shell not in SUPPORTED_DIRECT_SHELLS:
            raise ValueError(
                f"Skill '{skill.manifest.name}' requires shell '{normalized_shell}', "
                "but direct skill invocation in this runtime supports PowerShell only."
            )

    def require_workflow_skill(self, name: str) -> LoadedSkill:
        skill = self.require_user_invocable_skill(name)
        if not skill.manifest.workflow_profile:
            raise ValueError(f"Skill '{skill.manifest.name}' does not define a workflow profile.")
        return skill

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
        allow_model_invocation: bool = True,
    ) -> SkillRuntimeConfig:
        skill = self.resolve_skill(skill_name)
        if allow_model_invocation:
            skill = self.require_direct_prompt_skill(skill.manifest.name)
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
            model_name=skill.manifest.model,
            reasoning_effort=skill.manifest.effort,
            preferred_shell=self._normalize_shell(skill.manifest.shell),
            user_invocable=skill.manifest.is_user_invocable,
            disable_model_invocation=bool(skill.manifest.disable_model_invocation),
            workflow_profile=skill.manifest.workflow_profile,
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

    def _normalize_shell(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None
