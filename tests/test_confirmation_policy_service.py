from pathlib import Path
import json

from agent.settings import Settings
from app.confirmation_policy_service import (
    ConfirmationPolicyService,
    RiskPolicyConfigurationError,
)
from models.risk_policy import ConfirmationDecisionStatus, RiskLevel


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_confirmation_policy_defaults_and_unknown_fallback(tmp_path):
    service = ConfirmationPolicyService.from_settings(build_settings(tmp_path))

    safe_decision, safe_payload = service.build_confirmation_decision(action_name="dns_lookup")
    unknown_decision, unknown_payload = service.build_confirmation_decision(action_name="unknown_new_action")

    assert safe_decision.status == ConfirmationDecisionStatus.AUTO_ALLOWED
    assert safe_payload is None
    assert unknown_decision.status == ConfirmationDecisionStatus.CONFIRMATION_REQUIRED
    assert unknown_decision.risk_level == RiskLevel.ELEVATED
    assert unknown_payload is not None
    assert unknown_payload.action_name == "unknown_new_action"


def test_confirmation_policy_uses_project_override_config(tmp_path):
    settings = build_settings(tmp_path)
    settings.risk_policy_path.parent.mkdir(parents=True, exist_ok=True)
    settings.risk_policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "confirmation": {
                    "safe": "auto",
                    "elevated": "confirm",
                    "dangerous": "confirm",
                },
                "limits": {
                    "small_port_scan_max_ports_per_target": 10,
                    "small_port_scan_max_targets": 2,
                    "safe_batch_max_targets": 5,
                },
                "actions": {
                    "dns_lookup": {"risk": "safe"},
                    "http_probe": {"risk": "safe"},
                    "tls_inspect": {"risk": "safe"},
                    "banner_grab": {"risk": "safe"},
                    "port_scan_small": {"risk": "safe"},
                    "port_scan_large": {"risk": "elevated"},
                    "directory_scan_large": {"risk": "elevated"},
                    "poc_execute": {"risk": "dangerous"},
                },
                "overrides": {
                    "actions": {
                        "http_probe": {"risk": "dangerous"},
                    },
                    "modules": {},
                },
            }
        ),
        encoding="utf-8",
    )
    service = ConfirmationPolicyService.from_settings(settings)

    decision, payload = service.build_confirmation_decision(action_name="http_probe")

    assert decision.risk_level == RiskLevel.DANGEROUS
    assert decision.requires_confirmation
    assert payload is not None
    assert payload.risk_level == RiskLevel.DANGEROUS


def test_confirmation_policy_invalid_config_fails_closed(tmp_path):
    settings = build_settings(tmp_path)
    settings.risk_policy_path.parent.mkdir(parents=True, exist_ok=True)
    settings.risk_policy_path.write_text(
        json.dumps({"version": 2}),
        encoding="utf-8",
    )
    service = ConfirmationPolicyService.from_settings(settings)

    try:
        service.build_confirmation_decision(action_name="dns_lookup")
    except RiskPolicyConfigurationError as exc:
        assert "version" in str(exc)
    else:
        raise AssertionError("Expected RiskPolicyConfigurationError for invalid config.")
