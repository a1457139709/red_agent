from __future__ import annotations

from typing import Any

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

from .skill_service import SkillRuntimeConfig, SkillService


class CapabilityValidationError(ValueError):
    pass


class CapabilityService:
    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        skill_service: SkillService | None = None,
    ) -> None:
        self.registry = registry
        self.skill_service = skill_service

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        skill_service: SkillService | None = None,
    ) -> "CapabilityService":
        settings = settings or get_settings()
        registry = CapabilityRegistry.built_in_and_local(
            local_root=settings.app_data_dir / "capabilities",
            known_tool_names=set(build_tool_registry().keys()),
        )
        return cls(registry, skill_service=skill_service)

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

    async def build_prompt_assist_runtime_config(
        self,
        *,
        capability_name: str,
        context_summary: str,
        allow_model_invocation: bool = True,
    ) -> SkillRuntimeConfig:
        capability = self.require_capability(capability_name)
        if capability.manifest.kind != CapabilityKind.SKILL:
            raise CapabilityValidationError(
                f"Capability '{capability.manifest.name}' is not a skill."
            )
        if capability.manifest.execution.style != CapabilityExecutionStyle.PROMPT_ASSIST:
            raise CapabilityValidationError(
                f"Capability '{capability.manifest.name}' is not prompt-assist."
            )
        if self.skill_service is None:
            raise CapabilityValidationError(
                "Prompt-assist capabilities require a legacy SkillService bridge in Phase 5."
            )
        if self.skill_service.get_skill(capability.manifest.name) is None:
            raise CapabilityValidationError(
                f"Prompt-assist capability '{capability.manifest.name}' has no legacy SKILL.md bridge."
            )
        return await self.skill_service.build_skill_runtime_config(
            skill_name=capability.manifest.name,
            context_summary=context_summary,
            allow_model_invocation=allow_model_invocation,
        )

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
