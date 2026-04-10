from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
from typing import Any

from agent.settings import Settings, get_settings
from models.risk_policy import (
    ActionRiskPolicy,
    ConfirmationDecision,
    ConfirmationDecisionStatus,
    ConfirmationMode,
    ConfirmationRequestPayload,
    RiskLevel,
    RiskPolicyConfig,
    RiskPolicyLimits,
)


class RiskPolicyConfigurationError(ValueError):
    pass


DEFAULT_ACTION_RISK: dict[str, RiskLevel] = {
    "dns_lookup": RiskLevel.SAFE,
    "http_probe": RiskLevel.SAFE,
    "tls_inspect": RiskLevel.SAFE,
    "banner_grab": RiskLevel.SAFE,
    "port_scan_small": RiskLevel.SAFE,
    "batch_safe_probe": RiskLevel.SAFE,
    "port_scan_large": RiskLevel.ELEVATED,
    "directory_scan_large": RiskLevel.ELEVATED,
    "poc_execute": RiskLevel.DANGEROUS,
}

DEFAULT_CONFIRMATION: dict[RiskLevel, ConfirmationMode] = {
    RiskLevel.SAFE: ConfirmationMode.AUTO,
    RiskLevel.ELEVATED: ConfirmationMode.CONFIRM,
    RiskLevel.DANGEROUS: ConfirmationMode.CONFIRM,
}


@dataclass(frozen=True, slots=True)
class ActionRiskInput:
    action_name: str
    arguments: dict[str, Any]
    target_summary: str | None = None


class ConfirmationPolicyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ConfirmationPolicyService":
        return cls(settings or get_settings())

    def load_policy(self) -> RiskPolicyConfig:
        path = self.settings.risk_policy_path
        if not path.exists():
            return self._default_policy()
        return self._load_from_file(path)

    def classify_action(
        self,
        *,
        action_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[RiskLevel, str]:
        policy = self.load_policy()
        return self._classify_action_with_policy(
            policy,
            ActionRiskInput(action_name=action_name, arguments=dict(arguments or {})),
        )

    def build_confirmation_decision(
        self,
        *,
        action_name: str,
        arguments: dict[str, Any] | None = None,
        target_summary: str | None = None,
    ) -> tuple[ConfirmationDecision, ConfirmationRequestPayload | None]:
        policy = self.load_policy()
        risk_level, reason = self._classify_action_with_policy(
            policy,
            ActionRiskInput(
                action_name=action_name,
                arguments=dict(arguments or {}),
                target_summary=target_summary,
            ),
        )
        confirmation_mode = policy.confirmation[risk_level]
        if confirmation_mode == ConfirmationMode.AUTO:
            decision = ConfirmationDecision(
                status=ConfirmationDecisionStatus.AUTO_ALLOWED,
                action_name=action_name,
                risk_level=risk_level,
                confirmation_mode=confirmation_mode,
                requires_confirmation=False,
                reason=reason,
                message=f"Action '{action_name}' auto-allowed by risk policy.",
            )
            return decision, None
        decision = ConfirmationDecision(
            status=ConfirmationDecisionStatus.CONFIRMATION_REQUIRED,
            action_name=action_name,
            risk_level=risk_level,
            confirmation_mode=confirmation_mode,
            requires_confirmation=True,
            reason=reason,
            message=f"Action '{action_name}' requires confirmation ({risk_level.value}).",
        )
        payload = ConfirmationRequestPayload(
            action_name=action_name,
            risk_level=risk_level,
            target_summary=target_summary,
            reason=reason,
            message=decision.message,
        )
        return decision, payload

    def _classify_action_with_policy(
        self,
        policy: RiskPolicyConfig,
        action: ActionRiskInput,
    ) -> tuple[RiskLevel, str]:
        name = action.action_name
        if name == "port_scan":
            return self._classify_port_scan(policy, action.arguments)
        if name == "batch_probe":
            return self._classify_batch_probe(policy, action.arguments)
        if name in policy.action_overrides:
            return policy.action_overrides[name].risk, "action override"
        if name in policy.actions:
            return policy.actions[name].risk, "default action mapping"
        return RiskLevel.ELEVATED, "unknown redteam action defaults to elevated"

    def _classify_port_scan(
        self,
        policy: RiskPolicyConfig,
        arguments: dict[str, Any],
    ) -> tuple[RiskLevel, str]:
        ports = self._parse_port_count(arguments.get("ports"))
        targets = self._parse_target_count(arguments.get("targets"))
        if (
            ports <= policy.limits.small_port_scan_max_ports_per_target
            and targets <= policy.limits.small_port_scan_max_targets
        ):
            return RiskLevel.SAFE, "small port scan within policy limits"
        return RiskLevel.ELEVATED, "large port scan exceeds policy limits"

    def _classify_batch_probe(
        self,
        policy: RiskPolicyConfig,
        arguments: dict[str, Any],
    ) -> tuple[RiskLevel, str]:
        targets = self._parse_target_count(arguments.get("targets"))
        if targets <= policy.limits.safe_batch_max_targets:
            return RiskLevel.SAFE, "safe batch probe within target limit"
        return RiskLevel.ELEVATED, "batch probe target count exceeds limit"

    def _parse_port_count(self, raw_ports: Any) -> int:
        if raw_ports is None:
            return 0
        if isinstance(raw_ports, str):
            items = [item.strip() for item in raw_ports.split(",") if item.strip()]
            return len(items)
        if isinstance(raw_ports, (list, tuple, set)):
            return len(raw_ports)
        return 1

    def _parse_target_count(self, raw_targets: Any) -> int:
        if raw_targets is None:
            return 1
        if isinstance(raw_targets, str):
            items = [item.strip() for item in raw_targets.split(",") if item.strip()]
            return max(1, len(items))
        if isinstance(raw_targets, (list, tuple, set)):
            return max(1, len(raw_targets))
        if isinstance(raw_targets, int):
            return max(1, raw_targets)
        return 1

    def _default_policy(self) -> RiskPolicyConfig:
        return RiskPolicyConfig(
            version=1,
            confirmation=dict(DEFAULT_CONFIRMATION),
            limits=RiskPolicyLimits(),
            actions={name: ActionRiskPolicy(risk=risk) for name, risk in DEFAULT_ACTION_RISK.items()},
            action_overrides={},
            module_overrides={},
        )

    def _load_from_file(self, path: Path) -> RiskPolicyConfig:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RiskPolicyConfigurationError(f"Invalid risk policy JSON: {exc.msg}") from exc

        if not isinstance(payload, dict):
            raise RiskPolicyConfigurationError("Risk policy config must be a JSON object.")
        version = payload.get("version")
        if version != 1:
            raise RiskPolicyConfigurationError("Risk policy version must be 1.")
        confirmation = self._parse_confirmation(payload.get("confirmation"))
        limits = self._parse_limits(payload.get("limits"))
        actions = self._parse_actions(payload.get("actions"), field_name="actions")
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise RiskPolicyConfigurationError("Risk policy overrides must be an object.")
        action_overrides = self._parse_actions(overrides.get("actions"), field_name="overrides.actions")
        module_overrides = self._parse_actions(overrides.get("modules"), field_name="overrides.modules")
        return RiskPolicyConfig(
            version=1,
            confirmation=confirmation,
            limits=limits,
            actions=actions,
            action_overrides=action_overrides,
            module_overrides=module_overrides,
        )

    def _parse_confirmation(self, raw: Any) -> dict[RiskLevel, ConfirmationMode]:
        if not isinstance(raw, dict):
            raise RiskPolicyConfigurationError("confirmation must be an object.")
        parsed: dict[RiskLevel, ConfirmationMode] = {}
        for level in RiskLevel:
            if level.value not in raw:
                raise RiskPolicyConfigurationError(
                    f"confirmation missing required key '{level.value}'."
                )
            try:
                parsed[level] = ConfirmationMode(raw[level.value])
            except ValueError as exc:
                raise RiskPolicyConfigurationError(
                    f"confirmation value for '{level.value}' is invalid."
                ) from exc
        return parsed

    def _parse_limits(self, raw: Any) -> RiskPolicyLimits:
        if not isinstance(raw, dict):
            raise RiskPolicyConfigurationError("limits must be an object.")
        return RiskPolicyLimits(
            small_port_scan_max_ports_per_target=self._require_positive_int(
                raw.get("small_port_scan_max_ports_per_target"),
                field_name="limits.small_port_scan_max_ports_per_target",
            ),
            small_port_scan_max_targets=self._require_positive_int(
                raw.get("small_port_scan_max_targets"),
                field_name="limits.small_port_scan_max_targets",
            ),
            safe_batch_max_targets=self._require_positive_int(
                raw.get("safe_batch_max_targets"),
                field_name="limits.safe_batch_max_targets",
            ),
        )

    def _parse_actions(self, raw: Any, *, field_name: str) -> dict[str, ActionRiskPolicy]:
        if raw in (None, {}):
            return {}
        if not isinstance(raw, dict):
            raise RiskPolicyConfigurationError(f"{field_name} must be an object.")
        parsed: dict[str, ActionRiskPolicy] = {}
        for name, payload in raw.items():
            if not isinstance(name, str) or not name.strip():
                raise RiskPolicyConfigurationError(f"{field_name} contains an invalid action name.")
            if not isinstance(payload, dict):
                raise RiskPolicyConfigurationError(f"{field_name}.{name} must be an object.")
            try:
                risk = RiskLevel(payload["risk"])
            except (KeyError, ValueError) as exc:
                raise RiskPolicyConfigurationError(
                    f"{field_name}.{name}.risk must be one of safe/elevated/dangerous."
                ) from exc
            parsed[name.strip()] = ActionRiskPolicy(risk=risk)
        return parsed

    def _require_positive_int(self, value: Any, *, field_name: str) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise RiskPolicyConfigurationError(f"{field_name} must be an integer.") from exc
        if number <= 0 or not math.isfinite(number):
            raise RiskPolicyConfigurationError(f"{field_name} must be greater than 0.")
        return number
