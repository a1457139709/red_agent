from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re

from agent.settings import Settings, get_settings
from models.evidence import Evidence
from models.finding import Finding
from models.job import Job
from models.operation import Operation
from models.run import utc_now_iso
from tools.contracts import EvidenceCandidate, SecurityToolResult

from .evidence_service import EvidenceService
from .finding_service import FindingService


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "artifact"


@dataclass(frozen=True, slots=True)
class PersistedSecurityResult:
    evidence: list[Evidence] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    relative_path: str
    hash_digest: str
    content_type: str
    captured_at: str


class EvidenceArtifactManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def write_artifact(
        self,
        *,
        operation: Operation,
        job: Job | None,
        tool_name: str,
        candidate: EvidenceCandidate,
        ordinal: int,
        captured_at: str,
    ) -> EvidenceArtifact:
        evidence_dir = (
            self.settings.app_data_dir
            / "operations"
            / operation.public_id
            / "evidence"
        )
        evidence_dir.mkdir(parents=True, exist_ok=True)

        job_label = job.public_id if job is not None and job.public_id else "manual"
        file_name = f"{job_label}-{ordinal:02d}-{_slugify(candidate.evidence_type)}.json"
        artifact_path = evidence_dir / file_name
        envelope = {
            "evidence_type": candidate.evidence_type,
            "target_ref": candidate.target_ref,
            "title": candidate.title,
            "summary": candidate.summary,
            "source_tool": tool_name,
            "captured_at": captured_at,
            "content_type": candidate.content_type,
            "payload": candidate.payload,
        }
        encoded = (json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        artifact_path.write_bytes(encoded)
        relative_path = artifact_path.relative_to(self.settings.working_directory).as_posix()
        return EvidenceArtifact(
            relative_path=relative_path,
            hash_digest=f"sha256:{sha256(encoded).hexdigest()}",
            content_type="application/json",
            captured_at=captured_at,
        )


class EvidencePipelineService:
    def __init__(
        self,
        *,
        evidence_service: EvidenceService,
        finding_service: FindingService,
        artifact_manager: EvidenceArtifactManager,
        settings: Settings,
    ) -> None:
        self.evidence_service = evidence_service
        self.finding_service = finding_service
        self.artifact_manager = artifact_manager
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EvidencePipelineService":
        settings = settings or get_settings()
        return cls(
            evidence_service=EvidenceService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            artifact_manager=EvidenceArtifactManager(settings),
            settings=settings,
        )

    def persist_security_result(
        self,
        *,
        operation: Operation,
        job: Job,
        tool_name: str,
        result: SecurityToolResult,
    ) -> PersistedSecurityResult:
        evidence_records: list[Evidence] = []
        for index, candidate in enumerate(result.evidence_candidates, start=1):
            captured_at = utc_now_iso()
            artifact = self.artifact_manager.write_artifact(
                operation=operation,
                job=job,
                tool_name=tool_name,
                candidate=candidate,
                ordinal=index,
                captured_at=captured_at,
            )
            evidence_records.append(
                self.evidence_service.create_evidence(
                    operation_identifier=operation.id,
                    job_identifier=job.id,
                    evidence_type=candidate.evidence_type,
                    target_ref=candidate.target_ref,
                    title=candidate.title,
                    summary=candidate.summary,
                    artifact_path=artifact.relative_path,
                    content_type=artifact.content_type,
                    hash_digest=artifact.hash_digest,
                    captured_at=artifact.captured_at,
                )
            )

        finding_records: list[Finding] = []
        evidence_identifiers = [record.id for record in evidence_records]
        for candidate in result.finding_candidates:
            finding = self.finding_service.create_finding(
                operation_identifier=operation.id,
                source_job_identifier=job.id,
                finding_type=candidate.finding_type,
                title=candidate.title,
                target_ref=candidate.target_ref,
                severity=candidate.severity,
                confidence=candidate.confidence,
                summary=candidate.summary,
                impact=candidate.impact,
                reproduction_notes=candidate.reproduction_notes,
                next_action=candidate.next_action,
            )
            if evidence_identifiers:
                self.finding_service.link_evidence(
                    finding.id,
                    evidence_identifiers,
                )
            finding_records.append(finding)

        return PersistedSecurityResult(
            evidence=evidence_records,
            findings=finding_records,
        )
