from __future__ import annotations

from agent.settings import Settings, get_settings
from app.artifact_service import ArtifactService
from models.artifact import Artifact
from models.evidence import Evidence


class EvidenceService:
    def __init__(
        self,
        artifact_service: ArtifactService,
        settings: Settings,
    ) -> None:
        self.artifact_service = artifact_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EvidenceService":
        settings = settings or get_settings()
        return cls(
            ArtifactService.from_settings(settings),
            settings,
        )

    def create_evidence(
        self,
        *,
        operation_identifier: str,
        evidence_type: str,
        target_ref: str,
        title: str,
        summary: str,
        job_identifier: str | None = None,
        artifact_path: str | None = None,
        content_type: str | None = None,
        hash_digest: str | None = None,
        captured_at: str | None = None,
    ) -> Evidence:
        artifact = self.artifact_service.create_artifact(
            operation_identifier=operation_identifier,
            source_job_identifier=job_identifier,
            artifact_type=evidence_type,
            target_ref=target_ref,
            title=title,
            summary=summary,
            artifact_path=artifact_path,
            content_type=content_type,
            hash_digest=hash_digest,
            captured_at=captured_at,
        )
        return _artifact_to_evidence(artifact)

    def get_evidence(self, identifier: str) -> Evidence | None:
        artifact = self.artifact_service.get_artifact(identifier)
        if artifact is None:
            return None
        return _artifact_to_evidence(artifact)

    def require_evidence(self, identifier: str) -> Evidence:
        evidence = self.get_evidence(identifier)
        if evidence is None:
            raise ValueError(f"Evidence not found: {identifier}")
        return evidence

    def list_evidence(self, operation_identifier: str, *, limit: int | None = 50) -> list[Evidence]:
        return [
            _artifact_to_evidence(artifact)
            for artifact in self.artifact_service.list_artifacts(operation_identifier, limit=limit)
        ]

    def save_evidence(self, evidence: Evidence) -> Evidence:
        artifact = self.artifact_service.save_artifact(_evidence_to_artifact(evidence))
        return _artifact_to_evidence(artifact)


def _artifact_to_evidence(artifact: Artifact) -> Evidence:
    return Evidence(
        id=artifact.id,
        public_id=artifact.public_id,
        operation_id=artifact.session_id,
        job_id=artifact.source_job_id,
        evidence_type=artifact.artifact_type,
        target_ref=artifact.target_ref,
        title=artifact.title,
        summary=artifact.summary,
        artifact_path=artifact.artifact_path,
        content_type=artifact.content_type,
        hash_digest=artifact.hash_digest,
        captured_at=artifact.captured_at,
    )


def _evidence_to_artifact(evidence: Evidence) -> Artifact:
    return Artifact(
        id=evidence.id,
        public_id=evidence.public_id,
        session_id=evidence.operation_id,
        source_job_id=evidence.job_id,
        artifact_type=evidence.evidence_type,
        target_ref=evidence.target_ref,
        title=evidence.title,
        summary=evidence.summary,
        artifact_path=evidence.artifact_path,
        content_type=evidence.content_type,
        hash_digest=evidence.hash_digest,
        captured_at=evidence.captured_at,
        metadata={},
    )
