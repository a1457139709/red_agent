from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path

from agent.settings import Settings, get_settings
from models.artifact import Artifact
from models.finding import Finding
from models.job import Job
from models.run import utc_now_iso
from storage.session_paths import artifact_payload_relative_path, resolve_session_relative_path
from tools.contracts import EvidenceCandidate, SecurityToolResult

from .artifact_service import ArtifactService
from .finding_service import FindingService
from .session_service import SessionService


@dataclass(frozen=True, slots=True)
class PersistedSecurityResult:
    artifacts: list[Artifact] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def evidence(self) -> list[Artifact]:
        return self.artifacts


@dataclass(frozen=True, slots=True)
class ArtifactPayloadFile:
    relative_path: str
    hash_digest: str
    content_type: str
    captured_at: str


class ArtifactPayloadManager:
    def __init__(self, settings: Settings, session_service: SessionService) -> None:
        self.settings = settings
        self.session_service = session_service

    def write_artifact(
        self,
        *,
        session_id: str,
        job: Job | None,
        tool_name: str,
        candidate: EvidenceCandidate,
        ordinal: int,
        captured_at: str,
    ) -> ArtifactPayloadFile:
        session = self.session_service.require_session(session_id)
        job_label = job.public_id if job is not None and job.public_id else "manual"
        relative_path = artifact_payload_relative_path(
            source_job_label=job_label,
            ordinal=ordinal,
            artifact_type=candidate.evidence_type,
        )
        artifact_path = resolve_session_relative_path(
            self.settings,
            session_id=session.id,
            relative_path=relative_path,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "artifact_type": candidate.evidence_type,
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
        return ArtifactPayloadFile(
            relative_path=relative_path,
            hash_digest=f"sha256:{sha256(encoded).hexdigest()}",
            content_type="application/json",
            captured_at=captured_at,
        )

    def write_payload(
        self,
        *,
        session_id: str,
        job: Job | None,
        tool_name: str,
        candidate: EvidenceCandidate,
        ordinal: int,
        captured_at: str,
    ) -> ArtifactPayloadFile:
        return self.write_artifact(
            session_id=session_id,
            job=job,
            tool_name=tool_name,
            candidate=candidate,
            ordinal=ordinal,
            captured_at=captured_at,
        )


class EvidencePipelineService:
    def __init__(
        self,
        *,
        artifact_service: ArtifactService,
        finding_service: FindingService,
        artifact_manager: ArtifactPayloadManager,
        settings: Settings,
    ) -> None:
        self.artifact_service = artifact_service
        self.finding_service = finding_service
        self.artifact_manager = artifact_manager
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EvidencePipelineService":
        settings = settings or get_settings()
        session_service = SessionService.from_settings(settings)
        return cls(
            artifact_service=ArtifactService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            artifact_manager=ArtifactPayloadManager(settings, session_service),
            settings=settings,
        )

    def persist_security_result(
        self,
        *,
        session_id: str,
        job: Job,
        tool_name: str,
        result: SecurityToolResult,
    ) -> PersistedSecurityResult:
        artifact_records: list[Artifact] = []
        for index, candidate in enumerate(result.evidence_candidates, start=1):
            captured_at = utc_now_iso()
            artifact_file = self.artifact_manager.write_artifact(
                session_id=session_id,
                job=job,
                tool_name=tool_name,
                candidate=candidate,
                ordinal=index,
                captured_at=captured_at,
            )
            artifact_records.append(
                self.artifact_service.create_artifact(
                    session_identifier=session_id,
                    source_job_identifier=job.id,
                    artifact_type=candidate.evidence_type,
                    target_ref=candidate.target_ref,
                    title=candidate.title,
                    summary=candidate.summary,
                    artifact_path=artifact_file.relative_path,
                    content_type=artifact_file.content_type,
                    hash_digest=artifact_file.hash_digest,
                    captured_at=artifact_file.captured_at,
                    metadata={"source_tool": tool_name},
                )
            )

        finding_records: list[Finding] = []
        artifact_identifiers = [record.id for record in artifact_records]
        for candidate in result.finding_candidates:
            finding = self.finding_service.create_finding(
                session_identifier=session_id,
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
            if artifact_identifiers:
                self.finding_service.link_artifacts(finding.id, artifact_identifiers)
            finding_records.append(finding)

        return PersistedSecurityResult(
            artifacts=artifact_records,
            findings=finding_records,
        )
