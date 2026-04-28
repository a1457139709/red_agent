from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.capability import (
    CapabilityExecutionMetadata,
    CapabilityExecutionStyle,
    CapabilityKind,
    CapabilityManifest,
    CapabilityParameter,
    CapabilityParameterType,
    CapabilityRiskMetadata,
    CapabilitySessionSupport,
    CapabilityToolPolicy,
    LoadedCapability,
)
from models.risk_policy import RiskLevel
from models.session import SessionMode


class CapabilityLoadError(ValueError):
    """Raised when a capability.json file cannot be loaded or validated."""


def load_capability_from_file(manifest_file: Path) -> LoadedCapability:
    if manifest_file.name != "capability.json":
        raise CapabilityLoadError(f"Expected capability.json, got {manifest_file.name}")
    if not manifest_file.exists():
        raise CapabilityLoadError(f"Capability manifest not found: {manifest_file}")

    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CapabilityLoadError(f"{manifest_file}: invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise CapabilityLoadError(f"{manifest_file}: capability manifest must be a JSON object")

    root_dir = manifest_file.parent
    return LoadedCapability(
        manifest=_parse_manifest(payload, source=str(manifest_file)),
        root_dir=root_dir,
        manifest_file=manifest_file,
        references=_list_dir_files(root_dir / "references"),
        scripts=_list_dir_files(root_dir / "scripts"),
    )


def _parse_manifest(payload: dict[str, Any], *, source: str) -> CapabilityManifest:
    version = _require_int(payload, "version", source=source)
    if version != 1:
        raise CapabilityLoadError(f"{source}: version must be 1")

    return CapabilityManifest(
        version=version,
        name=_require_string(payload, "name", source=source),
        kind=_parse_enum(
            CapabilityKind,
            _require_string(payload, "kind", source=source),
            "kind",
            source,
        ),
        display_name=_require_string(payload, "display_name", source=source),
        description=_require_string(payload, "description", source=source),
        modes=tuple(
            _parse_enum(SessionMode, item, "modes", source)
            for item in _require_string_list(payload, "modes", source=source)
        ),
        parameters=tuple(
            _parse_parameter(item, source=f"{source}: parameters[{index}]")
            for index, item in enumerate(_require_object_list(payload, "parameters", source=source))
        ),
        tools=_parse_tools(_require_object(payload, "tools", source=source), source=source),
        risk=_parse_risk(_require_object(payload, "risk", source=source), source=source),
        execution=_parse_execution(_require_object(payload, "execution", source=source), source=source),
        session=_parse_session(_require_object(payload, "session", source=source), source=source),
    )


def _parse_parameter(payload: dict[str, Any], *, source: str) -> CapabilityParameter:
    return CapabilityParameter(
        name=_require_string(payload, "name", source=source),
        type=_parse_enum(
            CapabilityParameterType,
            _require_string(payload, "type", source=source),
            "type",
            source,
        ),
        required=_require_bool(payload, "required", source=source),
        description=_require_string(payload, "description", source=source),
        default=payload.get("default"),
        choices=tuple(payload.get("choices") or ()),
    )


def _parse_tools(payload: dict[str, Any], *, source: str) -> CapabilityToolPolicy:
    return CapabilityToolPolicy(
        allowed=tuple(_require_string_list(payload, "allowed", source=f"{source}: tools")),
    )


def _parse_risk(payload: dict[str, Any], *, source: str) -> CapabilityRiskMetadata:
    return CapabilityRiskMetadata(
        default=_parse_enum(
            RiskLevel,
            _require_string(payload, "default", source=f"{source}: risk"),
            "risk.default",
            source,
        ),
        actions=tuple(_require_string_list(payload, "actions", source=f"{source}: risk")),
    )


def _parse_execution(payload: dict[str, Any], *, source: str) -> CapabilityExecutionMetadata:
    return CapabilityExecutionMetadata(
        style=_parse_enum(
            CapabilityExecutionStyle,
            _require_string(payload, "style", source=f"{source}: execution"),
            "execution.style",
            source,
        ),
        profile=_require_string(payload, "profile", source=f"{source}: execution"),
    )


def _parse_session(payload: dict[str, Any], *, source: str) -> CapabilitySessionSupport:
    result_layers = _require_string_list(payload, "result_layers", source=f"{source}: session")
    unsupported_layers = sorted(
        layer for layer in result_layers if layer not in {"memory", "artifacts", "findings", "reports"}
    )
    if unsupported_layers:
        raise CapabilityLoadError(
            f"{source}: session.result_layers contains unsupported layers: {', '.join(unsupported_layers)}"
        )
    return CapabilitySessionSupport(
        supports_one_shot=_require_bool(payload, "supports_one_shot", source=f"{source}: session"),
        supports_persistent=_require_bool(payload, "supports_persistent", source=f"{source}: session"),
        result_layers=tuple(result_layers),
    )


def _require_object(payload: dict[str, Any], key: str, *, source: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise CapabilityLoadError(f"{source}: field '{key}' must be an object")
    return value


def _require_object_list(payload: dict[str, Any], key: str, *, source: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise CapabilityLoadError(f"{source}: field '{key}' must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise CapabilityLoadError(f"{source}: field '{key}' must contain objects")
    return value


def _require_string(payload: dict[str, Any], key: str, *, source: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityLoadError(f"{source}: missing or invalid string field '{key}'")
    return value.strip()


def _require_string_list(payload: dict[str, Any], key: str, *, source: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise CapabilityLoadError(f"{source}: field '{key}' must be a list of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CapabilityLoadError(f"{source}: field '{key}' must be a list of non-empty strings")
        normalized.append(item.strip())
    return normalized


def _require_bool(payload: dict[str, Any], key: str, *, source: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise CapabilityLoadError(f"{source}: field '{key}' must be a boolean")
    return value


def _require_int(payload: dict[str, Any], key: str, *, source: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise CapabilityLoadError(f"{source}: field '{key}' must be an integer")
    return value


def _parse_enum(enum_type, value: str, field_name: str, source: str):
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise CapabilityLoadError(
            f"{source}: field '{field_name}' must be one of: {allowed}"
        ) from exc


def _list_dir_files(path: Path) -> tuple[Path, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(item for item in path.iterdir() if item.is_file()))
