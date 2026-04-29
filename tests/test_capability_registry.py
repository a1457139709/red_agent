import json
from pathlib import Path

import pytest

from capabilities.loader import CapabilityLoadError
from capabilities.registry import CapabilityRegistry
from models.capability import CapabilityKind
from models.session import SessionMode


def write_capability(root: Path, name: str, **overrides) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "name": name,
        "kind": "skill",
        "display_name": name.title(),
        "description": f"{name} capability.",
        "modes": ["normal"],
        "parameters": [],
        "tools": {"allowed": ["read_file"]},
        "risk": {"default": "safe", "actions": []},
        "execution": {"style": "prompt_assist", "profile": name},
        "session": {
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": [],
        },
    }
    payload.update(overrides)
    path = directory / "capability.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    if payload["kind"] == "skill":
        (directory / "prompt.md").write_text(f"# {name}\n\nPrompt body.", encoding="utf-8")
    return path


def test_builtin_registry_discovers_skills_and_modules():
    registry = CapabilityRegistry.built_in()

    skills = registry.list_capabilities(kind=CapabilityKind.SKILL)
    modules = registry.list_capabilities(kind=CapabilityKind.MODULE)

    assert {capability.manifest.name for capability in skills} >= {
        "development-default",
        "git-auto-commit",
        "security-audit",
        "weather-query-example",
    }
    assert {capability.manifest.name for capability in modules} == {
        "surface-recon",
        "web-enum",
    }


def test_registry_filters_by_mode():
    registry = CapabilityRegistry.built_in()

    redteam_capabilities = registry.list_capabilities(mode=SessionMode.REDTEAM)

    assert {capability.manifest.name for capability in redteam_capabilities} >= {
        "security-audit",
        "surface-recon",
        "web-enum",
    }


def test_local_capability_overrides_builtin(tmp_path):
    local_root = tmp_path / "capabilities"
    write_capability(
        local_root,
        "surface-recon",
        kind="module",
        display_name="Local Surface Recon",
        description="Local override.",
        modes=["redteam"],
        tools={"allowed": ["dns_lookup"]},
        risk={"default": "safe", "actions": ["dns_lookup"]},
        execution={"style": "workflow", "profile": "surface-recon"},
        session={
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": ["artifacts"],
        },
    )
    registry = CapabilityRegistry.built_in_and_local(local_root=local_root)

    loaded = registry.require_capability("surface-recon")

    assert loaded.source == "local"
    assert loaded.manifest.display_name == "Local Surface Recon"
    assert loaded.manifest.tools.allowed == ("dns_lookup",)


def test_registry_reload_refreshes_cache(tmp_path):
    local_root = tmp_path / "capabilities"
    write_capability(local_root, "sample")
    registry = CapabilityRegistry(local_root)

    assert registry.require_capability("sample").manifest.description == "sample capability."

    write_capability(
        local_root,
        "sample",
        description="Updated sample capability.",
    )
    assert registry.require_capability("sample").manifest.description == "sample capability."

    registry.reload()

    assert registry.require_capability("sample").manifest.description == "Updated sample capability."


def test_registry_rejects_unknown_declared_tools(tmp_path):
    local_root = tmp_path / "capabilities"
    write_capability(local_root, "sample", tools={"allowed": ["missing_tool"]})
    registry = CapabilityRegistry(local_root, known_tool_names={"read_file"})

    with pytest.raises(CapabilityLoadError, match="unknown tools"):
        registry.list_capabilities()
