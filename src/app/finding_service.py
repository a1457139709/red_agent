from __future__ import annotations

from agent.settings import Settings, get_settings
from models.finding import Finding
from storage.repositories.findings import FindingRepository
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage


class FindingService:
    def __init__(
        self,
        repository: FindingRepository,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "FindingService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            FindingRepository(storage),
            OperationRepository(storage),
            JobRepository(storage),
            settings,
        )

    def create_finding(
        self,
        *,
        operation_identifier: str,
        finding_type: str,
        title: str,
        target_ref: str,
        severity: str,
        confidence: str,
        source_job_identifier: str | None = None,
        summary: str = "",
        impact: str = "",
        reproduction_notes: str = "",
        next_action: str = "",
    ) -> Finding:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        source_job_id: str | None = None
        if source_job_identifier is not None:
            job = self.job_repository.get(source_job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {source_job_identifier}")
            if job.operation_id != operation.id:
                raise ValueError("Finding source job must belong to the same operation.")
            source_job_id = job.id

        finding = Finding.create(
            operation_id=operation.id,
            source_job_id=source_job_id,
            finding_type=finding_type,
            title=title,
            target_ref=target_ref,
            severity=severity,
            confidence=confidence,
            summary=summary,
            impact=impact,
            reproduction_notes=reproduction_notes,
            next_action=next_action,
        )
        return self.repository.create(finding)

    def get_finding(self, identifier: str) -> Finding | None:
        return self.repository.get(identifier)

    def require_finding(self, identifier: str) -> Finding:
        finding = self.get_finding(identifier)
        if finding is None:
            raise ValueError(f"Finding not found: {identifier}")
        return finding

    def list_findings(self, operation_identifier: str, *, limit: int | None = 50) -> list[Finding]:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        return self.repository.list(operation.id, limit=limit)

    def save_finding(self, finding: Finding) -> Finding:
        return self.repository.update(finding)
