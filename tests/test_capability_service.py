import asyncio
import json
from pathlib import Path

import pytest

from app.capability_service import CapabilityService, CapabilityValidationError
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
        "metadata": {"category": "test"},
        "tools": {"allowed": ["read_file"]},
        "risk": {"default": "safe", "actions": []},
        "execution": {"style": "prompt_assist", "profile": name},
        "user_invocable": True,
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


def build_service(root: Path) -> CapabilityService:
    return CapabilityService(
        CapabilityRegistry(root, known_tool_names={"read_file", "dns_lookup", "http_probe"}),
        base_tool_names=["read_file", "dns_lookup", "http_probe"],
    )


def test_capability_service_lists_skills_modules_and_modes(tmp_path):
    write_capability(tmp_path, "audit-skill")
    write_capability(
        tmp_path,
        "surface-recon",
        kind="module",
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
    service = build_service(tmp_path)

    assert [capability.manifest.name for capability in service.list_skills()] == ["audit-skill"]
    assert [capability.manifest.name for capability in service.list_modules()] == ["surface-recon"]
    assert [capability.manifest.name for capability in service.list_modules(mode=SessionMode.REDTEAM)] == [
        "surface-recon"
    ]
    assert service.require_capability("surface-recon").manifest.kind == CapabilityKind.MODULE


def test_validate_parameters_applies_defaults_and_rejects_unknowns(tmp_path):
    write_capability(
        tmp_path,
        "surface-recon",
        kind="module",
        modes=["redteam"],
        parameters=[
            {
                "name": "target",
                "type": "string",
                "required": True,
                "description": "Target.",
            },
            {
                "name": "include_dns",
                "type": "boolean",
                "required": False,
                "description": "Include DNS.",
                "default": True,
            },
        ],
        tools={"allowed": ["dns_lookup"]},
        risk={"default": "safe", "actions": ["dns_lookup"]},
        execution={"style": "workflow", "profile": "surface-recon"},
        session={
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": ["artifacts"],
        },
    )
    service = build_service(tmp_path)

    assert service.validate_parameters("surface-recon", {"target": "example.com"}) == {
        "target": "example.com",
        "include_dns": True,
    }

    with pytest.raises(CapabilityValidationError, match="unknown parameters"):
        service.validate_parameters("surface-recon", {"target": "example.com", "operation_id": "O0001"})


def test_validate_parameters_rejects_missing_and_wrong_type(tmp_path):
    write_capability(
        tmp_path,
        "surface-recon",
        kind="module",
        modes=["redteam"],
        parameters=[
            {
                "name": "target",
                "type": "string",
                "required": True,
                "description": "Target.",
            }
        ],
        tools={"allowed": ["dns_lookup"]},
        risk={"default": "safe", "actions": ["dns_lookup"]},
        execution={"style": "workflow", "profile": "surface-recon"},
        session={
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": ["artifacts"],
        },
    )
    service = build_service(tmp_path)

    with pytest.raises(CapabilityValidationError, match="missing required parameter"):
        service.validate_parameters("surface-recon", {})
    with pytest.raises(CapabilityValidationError, match="must be string"):
        service.validate_parameters("surface-recon", {"target": 123})


def test_prompt_assist_runtime_config_reads_prompt_from_capability(tmp_path):
    write_capability(
        tmp_path,
        "development-default",
        shell="powershell",
        model="gpt-test",
        effort="medium",
    )
    service = build_service(tmp_path)

    runtime_config = asyncio.run(
        service.build_prompt_assist_runtime_config(
            capability_name="development-default",
            context_summary="ctx",
            allow_model_invocation=False,
        )
    )

    assert runtime_config.capability is not None
    assert runtime_config.capability.manifest.name == "development-default"
    assert "Prompt body." in runtime_config.system_prompt
    assert runtime_config.allowed_tools == ["read_file"]
    assert runtime_config.model_name == "gpt-test"
    assert runtime_config.reasoning_effort == "medium"
    assert runtime_config.preferred_shell == "powershell"


def test_prompt_assist_runtime_config_rejects_workflow_only_skill(tmp_path):
    write_capability(
        tmp_path,
        "workflow-skill",
        disable_model_invocation=True,
    )
    service = build_service(tmp_path)

    with pytest.raises(CapabilityValidationError, match="disables direct model invocation"):
        asyncio.run(
            service.build_prompt_assist_runtime_config(
                capability_name="workflow-skill",
                context_summary="ctx",
            )
        )
