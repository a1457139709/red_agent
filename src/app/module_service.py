from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models.capability import CapabilityKind, ModuleInvocationRequest
from models.session import Session, SessionMode

from .capability_service import CapabilityService, CapabilityValidationError


@dataclass(slots=True)
class ModuleService:
    capability_service: CapabilityService

    def list_modules(self, *, mode: SessionMode | str | None = None):
        return self.capability_service.list_modules(mode=mode)

    def require_module(self, module_name: str):
        module = self.capability_service.require_capability(module_name)
        if module.manifest.kind != CapabilityKind.MODULE:
            raise CapabilityValidationError(
                f"Capability '{module.manifest.name}' is not a module."
            )
        return module

    def prepare_invocation(
        self,
        *,
        module_name: str,
        parameters: dict[str, Any] | None = None,
        mode: SessionMode | str,
        one_shot: bool,
        session: Session | None = None,
    ) -> ModuleInvocationRequest:
        module = self.require_module(module_name)
        normalized_mode = SessionMode(mode)
        if normalized_mode not in module.manifest.modes:
            raise CapabilityValidationError(
                f"Module '{module.manifest.name}' does not support mode '{normalized_mode.value}'."
            )
        if one_shot:
            if not module.manifest.session.supports_one_shot:
                raise CapabilityValidationError(
                    f"Module '{module.manifest.name}' does not support one-shot invocation."
                )
            session_id = None
        else:
            if not module.manifest.session.supports_persistent:
                raise CapabilityValidationError(
                    f"Module '{module.manifest.name}' does not support persistent session invocation."
                )
            if session is None:
                raise CapabilityValidationError(
                    f"Module '{module.manifest.name}' requires a session for persistent invocation."
                )
            if session.mode != normalized_mode:
                raise CapabilityValidationError(
                    f"Module '{module.manifest.name}' requires a {normalized_mode.value} session."
                )
            session_id = session.id

        return self.capability_service.prepare_module_invocation(
            module_name=module_name,
            parameters=parameters,
            mode=normalized_mode,
            one_shot=one_shot,
            session_id=session_id,
        )
