from __future__ import annotations

from typing import Any
from pathlib import Path
import json
import os

from agent.settings import Settings, get_settings
from models.artifact import Artifact
from models.finding import Finding
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


class ReportCreationError(ValueError):
    def __init__(
        self,
        *,
        user_message: str,
        ai_prompt: str,
        ai_context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.ai_prompt = ai_prompt
        self.ai_context = dict(ai_context or {})


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
        requested_identifier = session_identifier or operation_identifier
        try:
            session_id = self._resolve_session_id(requested_identifier)
            session = self.session_service.require_session(session_id)
            resolved_artifacts = self._resolve_artifacts(
                session_id=session.id,
                artifact_identifiers=artifact_identifiers or [],
            )
            resolved_findings = self._resolve_findings(
                session_id=session.id,
                finding_identifiers=finding_identifiers or [],
            )

            report = Report.create(
                session_id=session.id,
                report_type=report_type,
                title=title,
                summary=summary,
                metadata=metadata,
            )
            report.artifact_path = report_output_relative_path(
                report_id=report.id,
                report_type=report_type,
                extension=output_extension,
            )

            output_path: Path | None = None
            connection = self.repository.storage.connect()
            try:
                connection.execute("BEGIN")
                self.repository._create_with_connection(connection, report)

                for artifact in resolved_artifacts:
                    self.artifact_link_repository._create_with_connection(
                        connection,
                        ReportArtifactLink.create(
                            session_id=session.id,
                            report_id=report.id,
                            artifact_id=artifact.id,
                        ),
                    )

                for finding in resolved_findings:
                    self.finding_link_repository._create_with_connection(
                        connection,
                        ReportFindingLink.create(
                            session_id=session.id,
                            report_id=report.id,
                            finding_id=finding.id,
                        ),
                    )

                if output_payload is not None:
                    output_path = resolve_session_relative_path(
                        self.settings,
                        session_id=session.id,
                        relative_path=report.artifact_path,
                    )
                    self._write_output(output_path, output_payload)

                connection.commit()
                return report
            except Exception:
                connection.rollback()
                if output_path is not None:
                    self._cleanup_output(output_path)
                raise
            finally:
                connection.close()
        except ReportCreationError:
            raise
        except Exception as exc:
            raise self._build_creation_error(
                requested_identifier=requested_identifier,
                report_type=report_type,
                title=title,
                summary=summary,
                artifact_identifiers=artifact_identifiers or [],
                finding_identifiers=finding_identifiers or [],
                cause=exc,
            ) from exc

    def get_report(self, identifier: str) -> Report | None:
        return self.repository.get(identifier)

    def require_report(self, identifier: str) -> Report:
        report = self.get_report(identifier)
        if report is None:
            raise ValueError(f"Report not found: {identifier}")
        return report

    def list_reports(self, session_identifier: str, *, limit: int | None = 50) -> list[Report]:
        return self.repository.list(self._resolve_session_id(session_identifier), limit=limit)

    def count_reports(self, session_identifier: str) -> int:
        return self.repository.count(self._resolve_session_id(session_identifier))

    def list_artifact_links(self, report_identifier: str) -> list[ReportArtifactLink]:
        report = self.require_report(report_identifier)
        return self.artifact_link_repository.list_for_report(report.id)

    def list_finding_links(self, report_identifier: str) -> list[ReportFindingLink]:
        report = self.require_report(report_identifier)
        return self.finding_link_repository.list_for_report(report.id)

    def _resolve_artifacts(
        self,
        *,
        session_id: str,
        artifact_identifiers: list[str],
    ) -> list[Artifact]:
        artifacts: list[Artifact] = []
        for artifact_identifier in artifact_identifiers:
            artifact = self.artifact_repository.get(artifact_identifier)
            if artifact is None:
                raise ValueError(f"Artifact not found: {artifact_identifier}")
            if artifact.session_id != session_id:
                raise ValueError("Report and artifact must belong to the same session.")
            artifacts.append(artifact)
        return artifacts

    def _resolve_findings(
        self,
        *,
        session_id: str,
        finding_identifiers: list[str],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for finding_identifier in finding_identifiers:
            finding = self.finding_repository.get(finding_identifier)
            if finding is None:
                raise ValueError(f"Finding not found: {finding_identifier}")
            if finding.session_id != session_id:
                raise ValueError("Report and finding must belong to the same session.")
            findings.append(finding)
        return findings

    def _write_output(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        if isinstance(payload, (dict, list)):
            encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        else:
            encoded = str(payload)
        try:
            temp_path.write_text(encoded, encoding="utf-8")
            os.replace(temp_path, path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _cleanup_output(self, path: Path) -> None:
        if path.exists():
            path.unlink()
        temp_path = path.with_name(path.name + ".tmp")
        if temp_path.exists():
            temp_path.unlink()

    def _build_creation_error(
        self,
        *,
        requested_identifier: str | None,
        report_type: str,
        title: str,
        summary: str,
        artifact_identifiers: list[str],
        finding_identifiers: list[str],
        cause: Exception,
    ) -> ReportCreationError:
        reason = str(cause)
        user_message = f"Report creation failed: {reason}"
        ai_context = {
            "requested_identifier": requested_identifier,
            "report_type": report_type,
            "title": title,
            "summary": summary,
            "artifact_identifiers": list(artifact_identifiers),
            "finding_identifiers": list(finding_identifiers),
            "reason": reason,
        }
        ai_prompt = (
            "Report creation failed.\n"
            f"Requested session reference: {requested_identifier or 'missing'}\n"
            f"Report type: {report_type}\n"
            f"Title: {title}\n"
            f"Summary: {summary}\n"
            f"Artifact identifiers: {artifact_identifiers}\n"
            f"Finding identifiers: {finding_identifiers}\n"
            f"Failure reason: {reason}\n"
            "Please inspect the report inputs, verify that all linked records belong to the same session, "
            "and confirm that no partial report state was persisted before retrying."
        )
        return ReportCreationError(
            user_message=user_message,
            ai_prompt=ai_prompt,
            ai_context=ai_context,
        )

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
        )
