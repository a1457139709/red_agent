from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


DEFAULT_SCAN_TIMEOUT_SECONDS = 300


@dataclass(frozen=True, slots=True)
class ToolConfig:
    name: str
    binary_path: str | None = None
    timeout_seconds: int = DEFAULT_SCAN_TIMEOUT_SECONDS
    templates_path: str | None = None
    default_wordlist: str | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolStatus:
    name: str
    available: bool
    path: str | None
    version: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ScannerArtifact:
    kind: str
    path: str
    content_type: str


@dataclass(frozen=True, slots=True)
class ScannerEvidenceCandidate:
    evidence_type: str
    title: str
    summary: str | None
    payload: dict[str, Any]
    content_ref: str | None = None


@dataclass(frozen=True, slots=True)
class AttackPathCandidate:
    stage: str
    title: str
    status: str = "open"
    source_ref: str | None = None
    next_action: str | None = None


@dataclass(frozen=True, slots=True)
class ScanExecutionResult:
    ok: bool
    argv: list[str]
    return_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    output_path: str | None
    summary: str
    structured: dict[str, Any]
    evidence: list[ScannerEvidenceCandidate] = field(default_factory=list)
    attack_path: list[AttackPathCandidate] = field(default_factory=list)
    artifacts: list[ScannerArtifact] = field(default_factory=list)
    error: str | None = None

    def to_task_result(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "argv": self.argv,
            "return_code": self.return_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "output_path": self.output_path,
            "summary": self.summary,
            "structured": self.structured,
            "evidence": [
                {
                    "evidence_type": item.evidence_type,
                    "title": item.title,
                    "summary": item.summary,
                    "payload": item.payload,
                    "content_ref": item.content_ref,
                }
                for item in self.evidence
            ],
            "attack_path": [
                {
                    "stage": item.stage,
                    "title": item.title,
                    "status": item.status,
                    "source_ref": item.source_ref,
                    "next_action": item.next_action,
                }
                for item in self.attack_path
            ],
            "artifacts": [
                {"kind": item.kind, "path": item.path, "content_type": item.content_type}
                for item in self.artifacts
            ],
            "error": self.error,
        }


class ScannerAdapter(Protocol):
    name: str
    task_type: str

    def build_argv(self, *, binary_path: str, input_data: dict[str, Any], output_path: Path) -> list[str]:
        ...

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        ...

    def parse_output(self, output_text: str) -> dict[str, Any]:
        ...

    def build_evidence(
        self,
        *,
        input_data: dict[str, Any],
        structured: dict[str, Any],
        output_path: Path,
    ) -> tuple[list[ScannerEvidenceCandidate], list[AttackPathCandidate]]:
        ...

    @property
    def output_filename(self) -> str:
        ...

    @property
    def output_content_type(self) -> str:
        ...
