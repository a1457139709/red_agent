from __future__ import annotations

from agent.settings import Settings, get_settings
from models.finding import Finding
from models.finding_artifact_link import FindingArtifactLink
from models.run import utc_now_iso
from storage.repositories.artifacts import ArtifactRepository
from storage.repositories.finding_artifact_links import FindingArtifactLinkRepository
from storage.repositories.findings import FindingRepository
from storage.repositories.jobs import JobRepository
from storage.sqlite import SQLiteStorage

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class FindingService:
    def __init__(
        self,
        repository: FindingRepository,
        artifact_repository: ArtifactRepository,
        link_repository: FindingArtifactLinkRepository,
        session_service: SessionService,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.artifact_repository = artifact_repository
        self.link_repository = link_repository
        self.session_service = session_service
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "FindingService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            FindingRepository(storage),
            ArtifactRepository(storage),
            FindingArtifactLinkRepository(storage),
            SessionService.from_settings(settings),
            JobRepository(storage),
            settings,
        )

    def create_finding(
        self,
        *,
        session_identifier: str,
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
        session_id = self._resolve_session_id(session_identifier)
        source_job_id: str | None = None
        if source_job_identifier is not None:
            job = self.job_repository.get(source_job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {source_job_identifier}")
            if job.session_id != session_id:
                raise ValueError("Finding source job must belong to the same session.")
            source_job_id = job.id

        finding = Finding.create(
            session_id=session_id,
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

    def list_findings(self, session_identifier: str, *, limit: int | None = 50) -> list[Finding]:
        return self.repository.list(self._resolve_session_id(session_identifier), limit=limit)

    def count_findings(self, session_identifier: str) -> int:
        return self.repository.count(self._resolve_session_id(session_identifier))

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

    def link_artifacts(
        self,
        finding_identifier: str,
        artifact_identifiers: list[str],
    ) -> list[FindingArtifactLink]:
        finding = self.require_finding(finding_identifier)
        links: list[FindingArtifactLink] = []
        for artifact_identifier in artifact_identifiers:
            artifact = self.artifact_repository.get(artifact_identifier)
            if artifact is None:
                raise ValueError(f"Artifact not found: {artifact_identifier}")
            if artifact.session_id != finding.session_id:
                raise ValueError("Finding and artifact must belong to the same session.")
            links.append(
                self.link_repository.create(
                    FindingArtifactLink.create(
                        session_id=finding.session_id,
                        finding_id=finding.id,
                        artifact_id=artifact.id,
                    )
                )
            )
        return links

    def list_links(self, session_identifier: str) -> list[FindingArtifactLink]:
        return self.link_repository.list(self._resolve_session_id(session_identifier))

    def list_artifact_links_for_finding(self, finding_identifier: str) -> list[FindingArtifactLink]:
        finding = self.require_finding(finding_identifier)
        return self.link_repository.list_for_finding(finding.id)

    def list_finding_links_for_artifact(self, artifact_identifier: str) -> list[FindingArtifactLink]:
        artifact = self.artifact_repository.get(artifact_identifier)
        if artifact is None:
            raise ValueError(f"Artifact not found: {artifact_identifier}")
        return self.link_repository.list_for_artifact(artifact.id)

    def _update_status(self, identifier: str, *, status: str) -> Finding:
        finding = self.require_finding(identifier)
        finding.status = type(finding.status)(status)
        finding.updated_at = utc_now_iso()
        return self.repository.update(finding)

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(self.session_service, identifier)


def _merge_dismissal_reason(existing: str, reason: str) -> str:
    prefix = "Dismissal reason: "
    if not existing:
        return prefix + reason
    if prefix + reason in existing:
        return existing
    return f"{existing}\n{prefix}{reason}"
