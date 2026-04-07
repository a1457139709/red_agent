from __future__ import annotations

from agent.settings import Settings, get_settings
from models.finding import Finding
from models.finding_evidence_link import FindingEvidenceLink
from models.run import utc_now_iso
from storage.repositories.evidence import EvidenceRepository
from storage.repositories.finding_evidence_links import FindingEvidenceLinkRepository
from storage.repositories.findings import FindingRepository
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage


class FindingService:
    def __init__(
        self,
        repository: FindingRepository,
        evidence_repository: EvidenceRepository,
        link_repository: FindingEvidenceLinkRepository,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.evidence_repository = evidence_repository
        self.link_repository = link_repository
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "FindingService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            FindingRepository(storage),
            EvidenceRepository(storage),
            FindingEvidenceLinkRepository(storage),
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

    def confirm_finding(self, identifier: str) -> Finding:
        return self._update_status(identifier, status="confirmed")

    def dismiss_finding(self, identifier: str, reason: str | None = None) -> Finding:
        finding = self._update_status(identifier, status="dismissed")
        if reason:
            finding.next_action = _merge_dismissal_reason(finding.next_action, reason)
            finding.updated_at = utc_now_iso()
            finding = self.repository.update(finding)
        return finding

    def link_evidence(
        self,
        finding_identifier: str,
        evidence_identifiers: list[str],
    ) -> list[FindingEvidenceLink]:
        finding = self.require_finding(finding_identifier)
        links: list[FindingEvidenceLink] = []
        for evidence_identifier in evidence_identifiers:
            evidence = self.evidence_repository.get(evidence_identifier)
            if evidence is None:
                raise ValueError(f"Evidence not found: {evidence_identifier}")
            if evidence.operation_id != finding.operation_id:
                raise ValueError("Finding and evidence must belong to the same operation.")
            links.append(
                self.link_repository.create(
                    FindingEvidenceLink.create(
                        operation_id=finding.operation_id,
                        finding_id=finding.id,
                        evidence_id=evidence.id,
                    )
                )
            )
        return links

    def list_links(self, operation_identifier: str) -> list[FindingEvidenceLink]:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        return self.link_repository.list(operation.id)

    def list_evidence_links_for_finding(self, finding_identifier: str) -> list[FindingEvidenceLink]:
        finding = self.require_finding(finding_identifier)
        return self.link_repository.list_for_finding(finding.id)

    def list_finding_links_for_evidence(self, evidence_identifier: str) -> list[FindingEvidenceLink]:
        evidence = self.evidence_repository.get(evidence_identifier)
        if evidence is None:
            raise ValueError(f"Evidence not found: {evidence_identifier}")
        return self.link_repository.list_for_evidence(evidence.id)

    def _update_status(self, identifier: str, *, status: str) -> Finding:
        finding = self.require_finding(identifier)
        finding.status = type(finding.status)(status)
        finding.updated_at = utc_now_iso()
        return self.repository.update(finding)


def _merge_dismissal_reason(existing: str, reason: str) -> str:
    prefix = "Dismissal reason: "
    if not existing:
        return prefix + reason
    if prefix + reason in existing:
        return existing
    return f"{existing}\n{prefix}{reason}"
