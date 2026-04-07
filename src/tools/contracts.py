from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import AdmissionRequest, AdditionalAdmissionTarget, TargetDescriptor

DEFAULT_SECURITY_TOOL_TIMEOUT_SECONDS = 10
MAX_SECURITY_TOOL_TIMEOUT_SECONDS = 60


def require_non_empty_target(target: str) -> str:
    normalized = target.strip()
    if not normalized:
        raise ValueError("Target is required.")
    return normalized


def normalize_timeout(timeout_seconds: object | None) -> int:
    if timeout_seconds in (None, ""):
        return DEFAULT_SECURITY_TOOL_TIMEOUT_SECONDS
    try:
        timeout = int(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be an integer.") from exc
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than 0.")
    if timeout > MAX_SECURITY_TOOL_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be less than or equal to {MAX_SECURITY_TOOL_TIMEOUT_SECONDS}."
        )
    return timeout


def normalize_port(port: object | None, *, field_name: str = "port") -> int | None:
    if port in (None, ""):
        return None
    try:
        value = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if value <= 0 or value > 65535:
        raise ValueError(f"{field_name} must be between 1 and 65535.")
    return value


def normalize_port_list(ports: object | None, *, field_name: str = "ports") -> list[int]:
    if ports in (None, ""):
        return []
    if isinstance(ports, str):
        raw_values = [item.strip() for item in ports.split(",") if item.strip()]
    elif isinstance(ports, (list, tuple, set)):
        raw_values = list(ports)
    else:
        raise ValueError(f"{field_name} must be a list or comma-separated string.")

    values: list[int] = []
    for raw_value in raw_values:
        port = normalize_port(raw_value, field_name=field_name)
        if port is None:
            continue
        if port not in values:
            values.append(port)
    return values


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    evidence_type: str
    target_ref: str
    title: str
    summary: str
    content_type: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FindingCandidate:
    finding_type: str
    title: str
    target_ref: str
    severity: str
    confidence: str
    summary: str = ""
    impact: str = ""
    reproduction_notes: str = ""
    next_action: str = ""


@dataclass(frozen=True, slots=True)
class SecurityToolResult:
    tool_name: str
    target: str
    summary: str
    payload: dict[str, Any]
    evidence_candidates: list[EvidenceCandidate] = field(default_factory=list)
    finding_candidates: list[FindingCandidate] = field(default_factory=list)

    def __str__(self) -> str:
        return self.summary


@dataclass(frozen=True, slots=True)
class ScopeTarget:
    target: str
    protocol: str | None = None
    port: int | None = None
    label: str | None = None

    def to_additional_admission_target(self) -> AdditionalAdmissionTarget:
        return AdditionalAdmissionTarget(
            raw_target=self.target,
            protocol=self.protocol,
            port=self.port,
            label=self.label,
        )


@dataclass(frozen=True, slots=True)
class SecurityToolInvocation:
    target: str
    timeout_seconds: int
    protocol: str | None = None
    port: int | None = None
    admission_target: str | None = None
    admission_protocol: str | None = None
    admission_port: int | None = None
    additional_scope_targets: tuple[ScopeTarget, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_args: dict[str, Any] = field(default_factory=dict)

    def to_admission_request(
        self,
        *,
        operation_id: str,
        job_id: str | None,
        tool_name: str,
        tool_category: str,
    ) -> AdmissionRequest:
        return AdmissionRequest(
            operation_id=operation_id,
            job_id=job_id,
            tool_name=tool_name,
            tool_category=tool_category,
            raw_target=self.admission_target or self.target,
            protocol=self.admission_protocol or self.protocol,
            port=self.admission_port if self.admission_port is not None else self.port,
            metadata=dict(self.metadata),
            additional_targets=tuple(
                target.to_additional_admission_target()
                for target in self.additional_scope_targets
            ),
        )


class SecurityTool(Protocol):
    name: str
    category: str

    def validate_invocation(
        self,
        *,
        target: str,
        arguments: Mapping[str, Any],
        policy: ScopePolicy,
    ) -> SecurityToolInvocation: ...

    def execute(
        self,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult: ...
