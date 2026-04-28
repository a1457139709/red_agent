import asyncio
import json
from pathlib import Path

import pytest

from app.capability_service import CapabilityService, CapabilityValidationError
from capabilities.registry import CapabilityRegistry
from models.capability import CapabilityKind
from models.session import SessionMode


class FakeSkillService:
    def __init__(self, names: set[str] | None = None) -> None:
        self.names = names or {"development-default"}
        self.calls = []

    def get_skill(self, name: str):
        return object() if name in self.names else None

    async def build_skill_runtime_config(
        self,
        *,
        skill_name: str,
        context_summary: str,
        allow_model_invocation: bool = True,
    ):
        self.calls.append(
            {
                "skill_name": skill_name,
                "context_summary": context_summary,
                "allow_model_invocation": allow_model_invocation,
            }
        )
        return {"runtime": skill_name}


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
    return path


def build_service(root: Path, *, skill_service=None) -> CapabilityService:
    return CapabilityService(
        CapabilityRegistry(root, known_tool_names={"read_file", "dns_lookup", "http_probe"}),
        skill_service=skill_service,
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


def test_prompt_assist_runtime_config_uses_legacy_skill_bridge(tmp_path):
    write_capability(tmp_path, "development-default")
    skill_service = FakeSkillService({"development-default"})
    service = build_service(tmp_path, skill_service=skill_service)

    runtime_config = asyncio.run(
        service.build_prompt_assist_runtime_config(
            capability_name="development-default",
            context_summary="ctx",
            allow_model_invocation=False,
        )
    )

    assert runtime_config == {"runtime": "development-default"}
    assert skill_service.calls == [
        {
            "skill_name": "development-default",
            "context_summary": "ctx",
            "allow_model_invocation": False,
        }
    ]


def test_prompt_assist_runtime_config_requires_legacy_skill_bridge(tmp_path):
    write_capability(tmp_path, "new-skill")
    service = build_service(tmp_path, skill_service=FakeSkillService({"development-default"}))

    with pytest.raises(CapabilityValidationError, match="no legacy SKILL.md bridge"):
        asyncio.run(
            service.build_prompt_assist_runtime_config(
                capability_name="new-skill",
                context_summary="ctx",
            )
        )
