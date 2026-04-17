from __future__ import annotations

from pathlib import Path
import json

from agent.settings import Settings, get_settings
from models.report import Report
from models.report_artifact_link import ReportArtifactLink
from models.report_finding_link import ReportFindingLink
from storage.repositories.operations import OperationRepository
from storage.repositories.reports import ReportRepository
from storage.repositories.report_artifact_links import ReportArtifactLinkRepository
from storage.repositories.report_finding_links import ReportFindingLinkRepository
from storage.repositories.artifacts import ArtifactRepository
from storage.repositories.findings import FindingRepository
from storage.sqlite import SQLiteStorage
from storage.session_paths import report_output_relative_path, resolve_session_relative_path

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class ReportService:
    def __init__(
        self,
        repository: ReportRepository,
        artifact_link_repository: ReportArtifactLinkRepository,
        finding_link_repository: ReportFindingLinkRepository,
        artifact_repository: ArtifactRepository,
        finding_repository: FindingRepository,
        session_service: SessionService,
        operation_repository: OperationRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.artifact_link_repository = artifact_link_repository
        self.finding_link_repository = finding_link_repository
        self.artifact_repository = artifact_repository
        self.finding_repository = finding_repository
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ReportService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            ReportRepository(storage),
            ReportArtifactLinkRepository(storage),
            ReportFindingLinkRepository(storage),
            ArtifactRepository(storage),
            FindingRepository(storage),
            SessionService.from_settings(settings),
            OperationRepository(storage),
            settings,
        )

    def create_report(
        self,
        *,
        session_identifier: str | None = None,
        operation_identifier: str | None = None,
        report_type: str,
        title: str,
        summary: str,
        artifact_identifiers: list[str] | None = None,
        finding_identifiers: list[str] | None = None,
        output_payload: object | None = None,
        output_extension: str = ".json",
        metadata: dict | None = None,
    ) -> Report:
        session_id = self._resolve_session_id(session_identifier or operation_identifier)
        session = self.session_service.require_session(session_id)
        report = Report.create(
            session_id=session.id,
            report_type=report_type,
            title=title,
            summary=summary,
            metadata=metadata,
        )
        report.artifact_path = report_output_relative_path(
            report_public_id="pending",
            report_type=report_type,
            extension=output_extension,
        )
        report = self.repository.create(report)
        report.artifact_path = report_output_relative_path(
            report_public_id=report.public_id,
            report_type=report_type,
            extension=output_extension,
        )
        report = self.repository.update(report)

        if output_payload is not None:
            path = resolve_session_relative_path(
                self.settings,
                session_public_id=session.public_id,
                relative_path=report.artifact_path,
            )
            self._write_output(path, output_payload)

        for artifact_identifier in artifact_identifiers or []:
            artifact = self.artifact_repository.get(artifact_identifier)
            if artifact is None:
                raise ValueError(f"Artifact not found: {artifact_identifier}")
            if artifact.session_id != session.id:
                raise ValueError("Report and artifact must belong to the same session.")
            self.artifact_link_repository.create(
                ReportArtifactLink.create(
                    session_id=session.id,
                    report_id=report.id,
                    artifact_id=artifact.id,
                )
            )

        for finding_identifier in finding_identifiers or []:
            finding = self.finding_repository.get(finding_identifier)
            if finding is None:
                raise ValueError(f"Finding not found: {finding_identifier}")
            if finding.session_id != session.id:
                raise ValueError("Report and finding must belong to the same session.")
            self.finding_link_repository.create(
                ReportFindingLink.create(
                    session_id=session.id,
                    report_id=report.id,
                    finding_id=finding.id,
                )
            )

        return report

    def get_report(self, identifier: str) -> Report | None:
        return self.repository.get(identifier)

    def require_report(self, identifier: str) -> Report:
        report = self.get_report(identifier)
        if report is None:
            raise ValueError(f"Report not found: {identifier}")
        return report

    def list_reports(self, session_identifier: str, *, limit: int | None = 50) -> list[Report]:
        return self.repository.list(self._resolve_session_id(session_identifier), limit=limit)

    def list_artifact_links(self, report_identifier: str) -> list[ReportArtifactLink]:
        report = self.require_report(report_identifier)
        return self.artifact_link_repository.list_for_report(report.id)

    def list_finding_links(self, report_identifier: str) -> list[ReportFindingLink]:
        report = self.require_report(report_identifier)
        return self.finding_link_repository.list_for_report(report.id)

    def _write_output(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        else:
            encoded = str(payload)
        path.write_text(encoded, encoding="utf-8")

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
        )
