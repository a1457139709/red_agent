from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from agent.prompt import assemble_system_prompt
from agent.settings import Settings, get_settings
from capabilities.registry import CapabilityRegistry
from models.capability import (
    CapabilityExecutionStyle,
    CapabilityKind,
    CapabilityParameter,
    CapabilityParameterType,
    LoadedCapability,
    ModuleInvocationRequest,
)
from models.session import SessionMode
from tools import build_tool_registry
from tools.policy import RuntimeSafetyPolicy
from tools.shells import ShellResolutionError, ensure_shell_available, normalize_shell_name


DEFAULT_SKILL_NAME = "development-default"


class CapabilityValidationError(ValueError):
    pass


@dataclass(slots=True)
class CapabilityRuntimeConfig:
    capability: LoadedCapability | None
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

    @property
    def skill(self) -> LoadedCapability | None:
        return self.capability


class CapabilityService:
    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        base_tool_names: list[str] | None = None,
        default_skill_name: str = DEFAULT_SKILL_NAME,
        default_task_skill_name: str | None = DEFAULT_SKILL_NAME,
    ) -> None:
        self.registry = registry
        self.base_tool_names = list(base_tool_names or sorted(registry.known_tool_names or ()))
        self.default_skill_name = default_skill_name
        self.default_task_skill_name = default_task_skill_name
        self.base_safety_policy = RuntimeSafetyPolicy.for_tool_names(self.base_tool_names)

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
    ) -> "CapabilityService":
        settings = settings or get_settings()
        tool_names = list(build_tool_registry().keys())
        registry = CapabilityRegistry.built_in_and_local(
            local_root=settings.capabilities_dir,
            known_tool_names=set(tool_names),
        )
        return cls(
            registry,
            base_tool_names=tool_names,
        )

    def reload(self) -> None:
        self.registry.reload()

    def list_capabilities(
        self,
        *,
        kind: CapabilityKind | str | None = None,
        mode: SessionMode | str | None = None,
    ) -> list[LoadedCapability]:
        return self.registry.list_capabilities(kind=kind, mode=mode)

    def list_skills(self, *, mode: SessionMode | str | None = None) -> list[LoadedCapability]:
        return self.list_capabilities(kind=CapabilityKind.SKILL, mode=mode)

    def list_modules(self, *, mode: SessionMode | str | None = None) -> list[LoadedCapability]:
        return self.list_capabilities(kind=CapabilityKind.MODULE, mode=mode)

    def get_capability(self, name: str) -> LoadedCapability | None:
        return self.registry.get_capability(name)

    def require_capability(self, name: str) -> LoadedCapability:
        return self.registry.require_capability(name)

    def get_skill(self, name: str) -> LoadedCapability | None:
        capability = self.get_capability(name)
        if capability is None or capability.manifest.kind != CapabilityKind.SKILL:
            return None
        return capability

    def require_skill(self, name: str) -> LoadedCapability:
        capability = self.require_capability(name)
        if capability.manifest.kind != CapabilityKind.SKILL:
            raise CapabilityValidationError(
                f"Capability '{capability.manifest.name}' is not a skill."
            )
        return capability

    def resolve_skill(self, skill_name: str | None) -> LoadedCapability:
        resolved_name = skill_name or self.default_skill_name
        if not resolved_name:
            raise CapabilityValidationError("Skill name is required.")
        return self.require_skill(resolved_name)

    def require_user_invocable_skill(self, name: str) -> LoadedCapability:
        capability = self.resolve_skill(name)
        if not capability.manifest.is_user_invocable:
            raise CapabilityValidationError(
                f"Skill '{capability.manifest.name}' is not user-invocable."
            )
        return capability

    def require_direct_prompt_skill(self, name: str) -> LoadedCapability:
        capability = self.require_user_invocable_skill(name)
        self.ensure_direct_prompt_allowed(capability)
        return capability

    def ensure_direct_prompt_allowed(self, capability: LoadedCapability) -> None:
        if not capability.manifest.allows_model_invocation:
            raise CapabilityValidationError(
                f"Skill '{capability.manifest.name}' disables direct model invocation."
            )
        normalized_shell = self._normalize_shell(capability.manifest.shell)
        if normalized_shell is None:
            return
        try:
            ensure_shell_available(normalized_shell)
        except ShellResolutionError as exc:
            raise CapabilityValidationError(
                f"Skill '{capability.manifest.name}' requires shell '{normalized_shell}', but {exc}"
            ) from exc

    async def build_base_runtime_config(
        self,
        *,
        context_summary: str,
    ) -> CapabilityRuntimeConfig:
        system_prompt = await assemble_system_prompt(context_prompt=context_summary)
        return CapabilityRuntimeConfig(
            capability=None,
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
    ) -> CapabilityRuntimeConfig:
        return await self.build_prompt_assist_runtime_config(
            capability_name=skill_name,
            context_summary=context_summary,
            allow_model_invocation=allow_model_invocation,
        )

    async def build_prompt_assist_runtime_config(
        self,
        *,
        capability_name: str,
        context_summary: str,
        allow_model_invocation: bool = True,
    ) -> CapabilityRuntimeConfig:
        capability = self.require_skill(capability_name)
        if capability.manifest.execution.style != CapabilityExecutionStyle.PROMPT_ASSIST:
            raise CapabilityValidationError(
                f"Capability '{capability.manifest.name}' is not prompt-assist."
            )
        if allow_model_invocation:
            capability = self.require_direct_prompt_skill(capability.manifest.name)
        system_prompt = await assemble_system_prompt(
            skill_prompt=capability.prompt_body,
            context_prompt=context_summary,
        )
        return CapabilityRuntimeConfig(
            capability=capability,
            system_prompt=system_prompt,
            allowed_tools=list(capability.manifest.tools.allowed),
            safety_policy=RuntimeSafetyPolicy.for_tool_names(
                capability.manifest.tools.allowed,
                base_policy=self.base_safety_policy,
            ),
            model_name=capability.manifest.model,
            reasoning_effort=capability.manifest.effort,
            preferred_shell=self._normalize_shell(capability.manifest.shell),
            user_invocable=capability.manifest.is_user_invocable,
            disable_model_invocation=bool(capability.manifest.disable_model_invocation),
        )

    def validate_parameters(
        self,
        capability: LoadedCapability | str,
        parameters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        loaded = self.require_capability(capability) if isinstance(capability, str) else capability
        raw_parameters = dict(parameters or {})
        parameter_map = loaded.manifest.parameter_map()

        unknown = sorted(set(raw_parameters) - set(parameter_map))
        if unknown:
            raise CapabilityValidationError(
                f"Capability '{loaded.manifest.name}' received unknown parameters: {', '.join(unknown)}"
            )

        normalized: dict[str, Any] = {}
        for parameter in loaded.manifest.parameters:
            if parameter.name in raw_parameters:
                value = raw_parameters[parameter.name]
            elif parameter.default is not None:
                value = parameter.default
            elif parameter.required:
                raise CapabilityValidationError(
                    f"Capability '{loaded.manifest.name}' missing required parameter: {parameter.name}"
                )
            else:
                continue

            normalized[parameter.name] = self._coerce_parameter_value(
                value,
                parameter,
                capability_name=loaded.manifest.name,
            )
        return normalized

    def prepare_module_invocation(
        self,
        *,
        module_name: str,
        parameters: dict[str, Any] | None,
        mode: SessionMode | str,
        one_shot: bool,
        session_id: str | None = None,
    ) -> ModuleInvocationRequest:
        module = self.require_capability(module_name)
        if module.manifest.kind != CapabilityKind.MODULE:
            raise CapabilityValidationError(
                f"Capability '{module.manifest.name}' is not a module."
            )
        normalized_mode = SessionMode(mode)
        normalized_parameters = self.validate_parameters(module, parameters)
        return ModuleInvocationRequest(
            module=module,
            parameters=normalized_parameters,
            mode=normalized_mode,
            one_shot=one_shot,
            session_id=session_id,
            execution_profile=module.manifest.execution.profile,
            execution_style=module.manifest.execution.style,
            allowed_tools=module.manifest.tools.allowed,
            risk_default=module.manifest.risk.default,
            risk_actions=module.manifest.risk.actions,
            result_layers=module.manifest.session.result_layers,
        )

    def _coerce_parameter_value(
        self,
        value: Any,
        parameter: CapabilityParameter,
        *,
        capability_name: str,
    ) -> Any:
        if not self._matches_parameter_type(value, parameter.type):
            raise CapabilityValidationError(
                f"Capability '{capability_name}' parameter '{parameter.name}' must be {parameter.type.value}."
            )
        if parameter.choices and value not in parameter.choices:
            raise CapabilityValidationError(
                f"Capability '{capability_name}' parameter '{parameter.name}' must be one of {list(parameter.choices)}."
            )
        return value

    def _matches_parameter_type(
        self,
        value: Any,
        expected_type: CapabilityParameterType,
    ) -> bool:
        if expected_type == CapabilityParameterType.STRING:
            return isinstance(value, str)
        if expected_type == CapabilityParameterType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == CapabilityParameterType.NUMBER:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == CapabilityParameterType.BOOLEAN:
            return isinstance(value, bool)
        if expected_type == CapabilityParameterType.ARRAY:
            return isinstance(value, list)
        if expected_type == CapabilityParameterType.OBJECT:
            return isinstance(value, dict)
        return False

    def _normalize_shell(self, value: str | None) -> str | None:
        return normalize_shell_name(value)
