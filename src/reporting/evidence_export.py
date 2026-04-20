from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from agent.settings import Settings, get_settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_service import project_session_to_operation
from app.report_service import ReportService
from app.scope_policy_service import ScopePolicyService
from app.session_scope import resolve_session_identifier
from app.session_service import SessionService
from models.run import utc_now_iso
from storage.repositories.operations import OperationRepository
from storage.session_paths import resolve_session_relative_path
from storage.sqlite import SQLiteStorage

from .findings_summary import (
    build_artifact_index_export,
    build_findings_export,
    build_operation_summary,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "export"


@dataclass(frozen=True, slots=True)
class OperationExportResult:
    session_id: str
    session_public_id: str
    export_dir: Path
    files: list[Path]

    @property
    def operation_id(self) -> str:
        return self.session_id

    @property
    def operation_public_id(self) -> str:
        return self.session_public_id


class EvidenceExportService:
    def __init__(
        self,
        *,
        operation_repository: OperationRepository,
        scope_policy_service: ScopePolicyService,
        session_service: SessionService,
        job_service: JobService,
        artifact_service: ArtifactService,
        finding_service: FindingService,
        report_service: ReportService,
        settings: Settings,
    ) -> None:
        self.operation_repository = operation_repository
        self.scope_policy_service = scope_policy_service
        self.session_service = session_service
        self.job_service = job_service
        self.artifact_service = artifact_service
        self.finding_service = finding_service
        self.report_service = report_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EvidenceExportService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            operation_repository=OperationRepository(storage),
            scope_policy_service=ScopePolicyService.from_settings(settings),
            session_service=SessionService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            artifact_service=ArtifactService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            report_service=ReportService.from_settings(settings),
            settings=settings,
        )

    def generate_operation_export(
        self,
        operation_identifier: str,
        export_name: str | None = None,
    ) -> OperationExportResult:
        session_id = resolve_session_identifier(
            self.session_service,
            operation_identifier,
            operation_repository=self.operation_repository,
        )
        session = self.session_service.require_session(session_id)
        policy = self.scope_policy_service.require_scope_policy_for_session(session.id)
        operation = project_session_to_operation(session, policy)
        jobs = self.job_service.list_jobs(session.id, limit=None)
        artifacts = self.artifact_service.list_artifacts(session.id, limit=None)
        findings = self.finding_service.list_findings(session.id, limit=None)
        links = self.finding_service.list_links(session.id)

        export_label = _slugify(export_name or utc_now_iso().replace(":", "-"))
        export_dir = self.settings.sessions_dir / session.id / "reports"
        export_dir.mkdir(parents=True, exist_ok=True)

        artifacts_by_id = {item.id: item for item in artifacts}
        findings_by_id = {item.id: item for item in findings}

        report_specs = [
            (
                "session_summary",
                f"{export_label}-session-summary",
                build_operation_summary(
                    session=session,
                    operation=operation,
                    policy=policy,
                    jobs=jobs,
                    artifacts=artifacts,
                    findings=findings,
                ),
            ),
            (
                "findings",
                f"{export_label}-findings",
                build_findings_export(
                    findings=findings,
                    links=links,
                    artifacts_by_id=artifacts_by_id,
                ),
            ),
            (
                "artifact_index",
                f"{export_label}-artifact-index",
                build_artifact_index_export(
                    artifacts=artifacts,
                    links=links,
                    findings_by_id=findings_by_id,
                ),
            ),
        ]
        files: list[Path] = []
        artifact_ids = [artifact.public_id or artifact.id for artifact in artifacts]
        finding_ids = [finding.public_id or finding.id for finding in findings]
        for report_type, title, payload in report_specs:
            report = self.report_service.create_report(
                session_identifier=session.id,
                report_type=report_type,
                title=title,
                summary=f"{title} generated for session {session.public_id}.",
                artifact_identifiers=artifact_ids,
                finding_identifiers=finding_ids,
                output_payload=payload,
                metadata={"export_label": export_label},
            )
            files.append(
                resolve_session_relative_path(
                    self.settings,
                    session_id=session.id,
                    relative_path=report.artifact_path or "",
                )
            )

        return OperationExportResult(
            session_id=session.id,
            session_public_id=session.public_id,
            export_dir=export_dir,
            files=files,
        )
