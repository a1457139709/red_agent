from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class CapabilityTier(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DESTRUCTIVE = "destructive"


TOOL_CAPABILITIES: dict[str, CapabilityTier] = {
    "list_dir": CapabilityTier.READ,
    "read_file": CapabilityTier.READ,
    "search": CapabilityTier.READ,
    "web_fetch": CapabilityTier.READ,
    "web_search": CapabilityTier.READ,
    "write_file": CapabilityTier.WRITE,
    "edit_file": CapabilityTier.WRITE,
    "bash": CapabilityTier.EXECUTE,
    "delete_file": CapabilityTier.DESTRUCTIVE,
}


@dataclass(frozen=True, slots=True)
class RuntimeSafetyPolicy:
    allowed_capabilities: frozenset[CapabilityTier]

    @classmethod
    def base(cls) -> "RuntimeSafetyPolicy":
        return cls(frozenset(CapabilityTier))

    @classmethod
    def for_tool_names(
        cls,
        tool_names: Iterable[str],
        *,
        base_policy: "RuntimeSafetyPolicy | None" = None,
    ) -> "RuntimeSafetyPolicy":
        allowed = frozenset(capabilities_for_tools(tool_names))
        if base_policy is not None:
            allowed = frozenset(base_policy.allowed_capabilities.intersection(allowed))
        return cls(allowed_capabilities=allowed)

    def allows(self, capability: CapabilityTier) -> bool:
        return capability in self.allowed_capabilities


@dataclass(frozen=True, slots=True)
class SafetyAuditEvent:
    event_type: str
    tool_name: str
    capability: CapabilityTier
    reason: str
    target: str | None = None
    command_risk: str | None = None

    def to_payload(self) -> dict[str, str]:
        payload = {
            "tool_name": self.tool_name,
            "capability": self.capability.value,
            "reason": self.reason,
        }
        if self.target:
            payload["target"] = self.target
        if self.command_risk:
            payload["command_risk"] = self.command_risk
        return payload


def get_tool_capability(tool_name: str) -> CapabilityTier:
    try:
        return TOOL_CAPABILITIES[tool_name]
    except KeyError as exc:
        raise ValueError(f"No safety capability registered for tool: {tool_name}") from exc


def capabilities_for_tools(tool_names: Iterable[str]) -> set[CapabilityTier]:
    return {get_tool_capability(tool_name) for tool_name in tool_names}
