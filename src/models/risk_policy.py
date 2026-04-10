from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    SAFE = "safe"
    ELEVATED = "elevated"
    DANGEROUS = "dangerous"


class ConfirmationMode(StrEnum):
    AUTO = "auto"
    CONFIRM = "confirm"


class ConfirmationDecisionStatus(StrEnum):
    AUTO_ALLOWED = "auto_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ActionRiskPolicy:
    risk: RiskLevel


@dataclass(frozen=True, slots=True)
class RiskPolicyLimits:
    small_port_scan_max_ports_per_target: int = 100
    small_port_scan_max_targets: int = 10
    safe_batch_max_targets: int = 25


@dataclass(frozen=True, slots=True)
class RiskPolicyConfig:
    version: int
    confirmation: dict[RiskLevel, ConfirmationMode]
    limits: RiskPolicyLimits
    actions: dict[str, ActionRiskPolicy]
    action_overrides: dict[str, ActionRiskPolicy] = field(default_factory=dict)
    module_overrides: dict[str, ActionRiskPolicy] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfirmationRequestPayload:
    action_name: str
    risk_level: RiskLevel
    target_summary: str | None
    reason: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "risk_level": self.risk_level.value,
            "target_summary": self.target_summary,
            "reason": self.reason,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    status: ConfirmationDecisionStatus
    action_name: str
    risk_level: RiskLevel
    confirmation_mode: ConfirmationMode
    requires_confirmation: bool
    reason: str
    message: str

    @property
    def is_blocked(self) -> bool:
        return self.status == ConfirmationDecisionStatus.BLOCKED
