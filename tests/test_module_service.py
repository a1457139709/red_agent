import json
from pathlib import Path

import pytest

from app.capability_service import CapabilityService, CapabilityValidationError
from app.module_service import ModuleService
from capabilities.registry import CapabilityRegistry
from models.capability import CapabilityExecutionStyle
from models.risk_policy import RiskLevel
from models.session import Session, SessionMode, SessionPersistenceMode, SessionStatus


def write_capability(root: Path, name: str, **overrides) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "name": name,
        "kind": "module",
        "display_name": name.title(),
        "description": f"{name} capability.",
        "modes": ["redteam"],
        "parameters": [
            {
                "name": "target",
                "type": "string",
                "required": True,
                "description": "Target.",
            }
        ],
        "tools": {"allowed": ["dns_lookup", "http_probe"]},
        "risk": {"default": "safe", "actions": ["dns_lookup", "http_probe"]},
        "execution": {"style": "workflow", "profile": name},
        "session": {
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": ["artifacts"],
        },
    }
    payload.update(overrides)
    path = directory / "capability.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def build_service(root: Path) -> ModuleService:
    capability_service = CapabilityService(
        CapabilityRegistry(root, known_tool_names={"read_file", "dns_lookup", "http_probe"})
    )
    return ModuleService(capability_service)


def build_session(*, mode: SessionMode = SessionMode.REDTEAM) -> Session:
    return Session.create(
        title="Redteam",
        goal="Inspect target",
        mode=mode,
        persistence_mode=SessionPersistenceMode.PERSISTENT,
        workspace="D:/workspace",
        status=SessionStatus.ACTIVE,
    )


def test_prepare_one_shot_module_invocation_has_no_operation_id(tmp_path):
    write_capability(tmp_path, "surface-recon")
    service = build_service(tmp_path)

    invocation = service.prepare_invocation(
        module_name="surface-recon",
        parameters={"target": "example.com"},
        mode=SessionMode.REDTEAM,
        one_shot=True,
    )

    assert invocation.module.manifest.name == "surface-recon"
    assert invocation.parameters == {"target": "example.com"}
    assert invocation.mode == SessionMode.REDTEAM
    assert invocation.one_shot
    assert invocation.session_id is None
    assert invocation.execution_profile == "surface-recon"
    assert invocation.execution_style == CapabilityExecutionStyle.WORKFLOW
    assert invocation.allowed_tools == ("dns_lookup", "http_probe")
    assert invocation.risk_default == RiskLevel.SAFE
    assert invocation.risk_actions == ("dns_lookup", "http_probe")
    assert invocation.result_layers == ("artifacts",)
    assert not hasattr(invocation, "operation_id")


def test_prepare_persistent_module_invocation_uses_session_context(tmp_path):
    write_capability(tmp_path, "surface-recon")
    service = build_service(tmp_path)
    session = build_session()

    invocation = service.prepare_invocation(
        module_name="surface-recon",
        parameters={"target": "example.com"},
        mode=SessionMode.REDTEAM,
        one_shot=False,
        session=session,
    )

    assert invocation.session_id == session.id
    assert not invocation.one_shot


def test_module_service_rejects_skill_capability(tmp_path):
    write_capability(
        tmp_path,
        "development-default",
        kind="skill",
        modes=["normal"],
        parameters=[],
        tools={"allowed": ["read_file"]},
        risk={"default": "safe", "actions": []},
        execution={"style": "prompt_assist", "profile": "development-default"},
        session={
            "supports_one_shot": True,
            "supports_persistent": True,
            "result_layers": [],
        },
    )
    service = build_service(tmp_path)

    with pytest.raises(CapabilityValidationError, match="not a module"):
        service.require_module("development-default")


def test_module_service_validates_mode_and_session_support(tmp_path):
    write_capability(
        tmp_path,
        "surface-recon",
        session={
            "supports_one_shot": True,
            "supports_persistent": False,
            "result_layers": ["artifacts"],
        },
    )
    service = build_service(tmp_path)

    with pytest.raises(CapabilityValidationError, match="does not support mode"):
        service.prepare_invocation(
            module_name="surface-recon",
            parameters={"target": "example.com"},
            mode=SessionMode.NORMAL,
            one_shot=True,
        )

    with pytest.raises(CapabilityValidationError, match="does not support persistent"):
        service.prepare_invocation(
            module_name="surface-recon",
            parameters={"target": "example.com"},
            mode=SessionMode.REDTEAM,
            one_shot=False,
            session=build_session(),
        )


def test_module_service_requires_session_for_persistent_invocation(tmp_path):
    write_capability(tmp_path, "surface-recon")
    service = build_service(tmp_path)

    with pytest.raises(CapabilityValidationError, match="requires a session"):
        service.prepare_invocation(
            module_name="surface-recon",
            parameters={"target": "example.com"},
            mode=SessionMode.REDTEAM,
            one_shot=False,
        )
