from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from domain.findings import FindingCandidate
from domain.operations import ScopePolicy


ToolResultStatus = Literal["succeeded", "failed", "blocked"]


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_type: str
    title: str
    summary: str
    content_type: str
    content: str | bytes
    filename_hint: str | None = None


@dataclass(frozen=True, slots=True)
class SecurityToolResult:
    status: ToolResultStatus
    summary: str
    structured_result: dict[str, Any]
    evidence_items: list[EvidenceItem]
    finding_candidates: list[FindingCandidate]
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PortScanRequest:
    operation_id: str
    target: str
    ports: list[int] | None = None
    port_ranges: list[str] | None = None
    scan_label: str | None = None
    timeout_seconds: int = 30
    validated_scope: ScopePolicy | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionReport:
    result: SecurityToolResult
    materialized_evidence: list[Any] = field(default_factory=list)


class TypedSecurityTool(Protocol):
    name: str

    def execute(self, request: Any) -> SecurityToolResult:
        ...


@dataclass(frozen=True, slots=True)
class PortScanBackendResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
