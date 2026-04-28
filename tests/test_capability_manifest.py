from pathlib import Path

from capabilities.loader import load_capability_from_file
from models.capability import (
    CapabilityExecutionStyle,
    CapabilityKind,
    CapabilityParameterType,
)
from models.risk_policy import RiskLevel
from models.session import SessionMode


def test_builtin_module_manifest_uses_target_capability_contract():
    root = Path(__file__).resolve().parents[1]
    loaded = load_capability_from_file(
        root / "src" / "capabilities" / "surface-recon" / "capability.json"
    )

    manifest = loaded.manifest

    assert manifest.version == 1
    assert manifest.kind == CapabilityKind.MODULE
    assert manifest.execution.style == CapabilityExecutionStyle.WORKFLOW
    assert manifest.execution.profile == "surface-recon"
    assert manifest.modes == (SessionMode.REDTEAM,)
    assert manifest.risk.default == RiskLevel.SAFE
    assert manifest.risk.actions == ("dns_lookup", "http_probe", "tls_inspect")
    assert manifest.session.supports_one_shot
    assert manifest.session.supports_persistent
    assert manifest.session.result_layers == ("artifacts",)
    assert manifest.parameter_map()["target"].type == CapabilityParameterType.STRING
    assert manifest.parameter_map()["target"].required


def test_builtin_skill_manifest_is_prompt_assist_skill():
    root = Path(__file__).resolve().parents[1]
    loaded = load_capability_from_file(
        root / "src" / "capabilities" / "development-default" / "capability.json"
    )

    manifest = loaded.manifest

    assert manifest.kind == CapabilityKind.SKILL
    assert manifest.execution.style == CapabilityExecutionStyle.PROMPT_ASSIST
    assert manifest.execution.profile == "development-default"
    assert manifest.modes == (SessionMode.NORMAL,)
    assert "read_file" in manifest.tools.allowed
