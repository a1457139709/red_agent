import json

import pytest

from capabilities.loader import CapabilityLoadError, load_capability_from_file
from models.capability import CapabilityKind
from models.session import SessionMode


def write_manifest(tmp_path, payload, *, dirname="sample"):
    root = tmp_path / dirname
    root.mkdir()
    path = root / "capability.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    if payload.get("kind") == "skill":
        (root / "prompt.md").write_text("# Prompt\n\nPrompt body.", encoding="utf-8")
    return path


def valid_payload(**overrides):
    payload = {
        "version": 1,
        "name": "sample",
        "kind": "skill",
        "display_name": "Sample",
        "description": "Sample capability.",
        "modes": ["normal"],
        "parameters": [
            {
                "name": "target",
                "type": "string",
                "required": True,
                "description": "Target to inspect.",
            }
        ],
        "tools": {"allowed": ["read_file"]},
        "risk": {"default": "safe", "actions": ["read_file"]},
        "execution": {"style": "prompt_assist", "profile": "sample"},
        "session": {
            "supports_one_shot": True,
            "supports_persistent": False,
            "result_layers": ["memory"],
        },
    }
    payload.update(overrides)
    return payload


def test_load_capability_from_file_loads_valid_manifest_and_paths(tmp_path):
    manifest_path = write_manifest(tmp_path, valid_payload())
    references_dir = manifest_path.parent / "references"
    scripts_dir = manifest_path.parent / "scripts"
    references_dir.mkdir()
    scripts_dir.mkdir()
    reference = references_dir / "README.md"
    script = scripts_dir / "helper.py"
    reference.write_text("reference", encoding="utf-8")
    script.write_text("script", encoding="utf-8")

    loaded = load_capability_from_file(manifest_path)

    assert loaded.manifest.name == "sample"
    assert loaded.manifest.kind == CapabilityKind.SKILL
    assert loaded.manifest.modes == (SessionMode.NORMAL,)
    assert loaded.references == (reference,)
    assert loaded.scripts == (script,)
    assert loaded.prompt_file == manifest_path.parent / "prompt.md"
    assert loaded.prompt_body == "# Prompt\n\nPrompt body."


def test_load_capability_from_file_rejects_invalid_enum(tmp_path):
    manifest_path = write_manifest(tmp_path, valid_payload(kind="extension"))

    with pytest.raises(CapabilityLoadError, match="field 'kind' must be one of"):
        load_capability_from_file(manifest_path)


def test_load_capability_from_file_rejects_invalid_parameter_schema(tmp_path):
    payload = valid_payload(parameters=[{"name": "target", "type": "string"}])
    manifest_path = write_manifest(tmp_path, payload)

    with pytest.raises(CapabilityLoadError, match="required"):
        load_capability_from_file(manifest_path)


def test_load_capability_from_file_rejects_invalid_risk_level(tmp_path):
    payload = valid_payload(risk={"default": "medium", "actions": ["read_file"]})
    manifest_path = write_manifest(tmp_path, payload)

    with pytest.raises(CapabilityLoadError, match="risk.default"):
        load_capability_from_file(manifest_path)


def test_load_capability_from_file_rejects_unknown_result_layer(tmp_path):
    payload = valid_payload(
        session={
            "supports_one_shot": True,
            "supports_persistent": False,
            "result_layers": ["everything"],
        }
    )
    manifest_path = write_manifest(tmp_path, payload)

    with pytest.raises(CapabilityLoadError, match="unsupported layers"):
        load_capability_from_file(manifest_path)


def test_load_capability_from_file_requires_prompt_body_for_skills(tmp_path):
    manifest_path = write_manifest(tmp_path, valid_payload())
    (manifest_path.parent / "prompt.md").unlink()

    with pytest.raises(CapabilityLoadError, match="require prompt.md"):
        load_capability_from_file(manifest_path)
