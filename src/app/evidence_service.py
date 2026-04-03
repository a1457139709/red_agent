from __future__ import annotations

from agent.settings import Settings, get_settings
from models.evidence import Evidence
from storage.repositories.evidence import EvidenceRepository
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage


class EvidenceService:
    def __init__(
        self,
        repository: EvidenceRepository,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EvidenceService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            EvidenceRepository(storage),
            OperationRepository(storage),
            JobRepository(storage),
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
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        job_id: str | None = None
        if job_identifier is not None:
            job = self.job_repository.get(job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {job_identifier}")
            if job.operation_id != operation.id:
                raise ValueError("Evidence job must belong to the same operation.")
            job_id = job.id

        evidence = Evidence.create(
            operation_id=operation.id,
            job_id=job_id,
            evidence_type=evidence_type,
            target_ref=target_ref,
            title=title,
            summary=summary,
            artifact_path=artifact_path,
            content_type=content_type,
            hash_digest=hash_digest,
            captured_at=captured_at,
        )
        return self.repository.create(evidence)

    def get_evidence(self, identifier: str) -> Evidence | None:
        return self.repository.get(identifier)

    def require_evidence(self, identifier: str) -> Evidence:
        evidence = self.get_evidence(identifier)
        if evidence is None:
            raise ValueError(f"Evidence not found: {identifier}")
        return evidence

    def list_evidence(self, operation_identifier: str, *, limit: int | None = 50) -> list[Evidence]:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        return self.repository.list(operation.id, limit=limit)

    def save_evidence(self, evidence: Evidence) -> Evidence:
        return self.repository.update(evidence)
