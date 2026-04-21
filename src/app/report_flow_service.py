from __future__ import annotations

from dataclasses import dataclass, field

from agent.settings import Settings, get_settings
from models.report import Report

from .artifact_service import ArtifactService
from .finding_service import FindingService
from .operation_service import project_session_to_operation
from .report_service import ReportService
from .scope_policy_service import ScopePolicyService
from .session_record_query_service import SessionRecordQueryService
from .session_service import SessionService


@dataclass(frozen=True, slots=True)
class ReportFlowResult:
    report: Report
    reused: bool
    linked_artifact_ids: list[str] = field(default_factory=list)
    linked_finding_ids: list[str] = field(default_factory=list)


class ReportFlowService:
    def __init__(
        self,
        *,
        report_service: ReportService,
        session_service: SessionService,
        session_record_query_service: SessionRecordQueryService,
        scope_policy_service: ScopePolicyService,
        artifact_service: ArtifactService,
        finding_service: FindingService,
        settings: Settings,
    ) -> None:
        self.report_service = report_service
        self.session_service = session_service
        self.session_record_query_service = session_record_query_service
        self.scope_policy_service = scope_policy_service
        self.artifact_service = artifact_service
        self.finding_service = finding_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ReportFlowService":
        settings = settings or get_settings()
        return cls(
            report_service=ReportService.from_settings(settings),
            session_service=SessionService.from_settings(settings),
            session_record_query_service=SessionRecordQueryService.from_settings(settings),
            scope_policy_service=ScopePolicyService.from_settings(settings),
            artifact_service=ArtifactService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            settings=settings,
        )

    def get_or_create_session_summary(
        self,
        session_identifier: str,
    ) -> ReportFlowResult:
        session = self.session_service.require_session(session_identifier)
        existing = self._find_reusable_report(session.id, report_type="session_summary")
        if existing is not None:
            return self._build_result(existing, reused=True)

        history = self.session_record_query_service.get_history_summary(session.id, limit=10)
        payload = {
            "session": {
                "id": session.id,
                "public_id": session.public_id,
                "title": session.title,
                "goal": session.goal,
                "mode": session.mode.value,
                "status": session.status.value,
                "workspace": session.workspace,
                "target_summary": session.target_summary,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "closed_at": session.closed_at,
                "last_error": session.last_error,
            },
            "counts": {
                "runs": history.layer_summary.runs,
                "logs": history.layer_summary.logs,
                "checkpoints": history.layer_summary.checkpoints,
                "jobs": history.layer_summary.jobs,
                "events": history.layer_summary.events,
                "memory_entries": history.layer_summary.memory_entries,
                "artifacts": history.layer_summary.artifacts,
                "findings": history.layer_summary.findings,
                "reports": history.layer_summary.reports,
            },
            "recent_records": {
                "runs": [run.public_id for run in history.recent_runs],
                "jobs": [job.public_id for job in history.recent_jobs],
                "artifacts": [artifact.public_id for artifact in history.recent_artifacts],
                "findings": [finding.public_id for finding in history.recent_findings],
                "reports": [report.public_id for report in history.recent_reports],
            },
        }

        policy = self.scope_policy_service.get_scope_policy_for_session(session.id)
        if policy is not None:
            payload["scope_policy"] = {
                "allowed_hosts": policy.allowed_hosts,
                "allowed_domains": policy.allowed_domains,
                "allowed_cidrs": policy.allowed_cidrs,
                "allowed_ports": policy.allowed_ports,
                "allowed_protocols": policy.allowed_protocols,
                "denied_targets": policy.denied_targets,
                "allowed_tool_categories": policy.allowed_tool_categories,
                "max_concurrency": policy.max_concurrency,
                "rate_limit_per_minute": policy.rate_limit_per_minute,
                "confirmation_required_actions": policy.confirmation_required_actions,
            }
            operation = project_session_to_operation(session, policy)
            payload["operation"] = {
                "id": operation.id,
                "public_id": operation.public_id,
                "title": operation.title,
                "objective": operation.objective,
                "workspace": operation.workspace,
                "status": operation.status.value,
            }

        artifacts = self.session_record_query_service.list_artifacts(session.id, limit=None)
        findings = self.session_record_query_service.list_findings(session.id, limit=None)
        report = self.report_service.create_report(
            session_identifier=session.id,
            report_type="session_summary",
            title=f"Session summary for {session.public_id}",
            summary=f"Session summary generated for session {session.public_id}.",
            artifact_identifiers=[artifact.public_id for artifact in artifacts],
            finding_identifiers=[finding.public_id for finding in findings],
            output_payload=payload,
            metadata={"report_flow": "session_summary"},
        )
        return self._build_result(report, reused=False)

    def get_or_create_findings_summary(
        self,
        session_identifier: str,
    ) -> ReportFlowResult:
        session = self.session_service.require_session(session_identifier)
        existing = self._find_reusable_report(session.id, report_type="findings_summary")
        if existing is not None:
            return self._build_result(existing, reused=True)

        findings = self.session_record_query_service.list_findings(session.id, limit=None)
        artifacts = self.session_record_query_service.list_artifacts(session.id, limit=None)
        artifact_map = {artifact.id: artifact for artifact in artifacts}
        links = self.finding_service.list_links(session.id)

        findings_payload = []
        linked_artifact_ids: set[str] = set()
        for finding in findings:
            artifact_public_ids = [
                artifact_map[link.artifact_id].public_id
                for link in links
                if link.finding_id == finding.id and link.artifact_id in artifact_map
            ]
            linked_artifact_ids.update(artifact_public_ids)
            findings_payload.append(
                {
                    "finding_id": finding.public_id,
                    "finding_type": finding.finding_type,
                    "title": finding.title,
                    "target_ref": finding.target_ref,
                    "severity": finding.severity,
                    "confidence": finding.confidence,
                    "status": finding.status.value,
                    "summary": finding.summary,
                    "impact": finding.impact,
                    "reproduction_notes": finding.reproduction_notes,
                    "next_action": finding.next_action,
                    "source_job_id": finding.source_job_id,
                    "artifact_public_ids": artifact_public_ids,
                }
            )

        payload = {
            "session": {
                "id": session.id,
                "public_id": session.public_id,
                "title": session.title,
                "status": session.status.value,
            },
            "counts": {
                "findings": len(findings),
                "artifacts": len(artifacts),
            },
            "findings": findings_payload,
        }
        report = self.report_service.create_report(
            session_identifier=session.id,
            report_type="findings_summary",
            title=f"Findings summary for {session.public_id}",
            summary=f"Findings summary generated for session {session.public_id}.",
            artifact_identifiers=[artifact.public_id for artifact in artifacts],
            finding_identifiers=[finding.public_id for finding in findings],
            output_payload=payload,
            metadata={"report_flow": "findings_summary"},
        )
        return self._build_result(
            report,
            reused=False,
            fallback_artifact_ids=sorted(linked_artifact_ids),
            fallback_finding_ids=[finding.public_id for finding in findings],
        )

    def get_or_create_operator_report(
        self,
        session_identifier: str,
    ) -> ReportFlowResult:
        session = self.session_service.require_session(session_identifier)
        existing = self._find_reusable_report(session.id, report_type="operator_report")
        if existing is not None:
            return self._build_result(existing, reused=True)

        history = self.session_record_query_service.get_history_summary(session.id, limit=10)
        findings = self.session_record_query_service.list_findings(session.id, limit=10)
        artifacts = self.session_record_query_service.list_artifacts(session.id, limit=10)
        reports = self.session_record_query_service.list_reports(session.id, limit=10)

        lines = [
            f"# Operator Report: {session.title}",
            "",
            f"Session: {session.public_id}",
            f"Mode: {session.mode.value}",
            f"Status: {session.status.value}",
            f"Goal: {session.goal}",
            f"Target Summary: {session.target_summary or '-'}",
            "",
            "## Record Counts",
            f"- Runs: {history.layer_summary.runs}",
            f"- Logs: {history.layer_summary.logs}",
            f"- Checkpoints: {history.layer_summary.checkpoints}",
            f"- Jobs: {history.layer_summary.jobs}",
            f"- Events: {history.layer_summary.events}",
            f"- Memory Entries: {history.layer_summary.memory_entries}",
            f"- Artifacts: {history.layer_summary.artifacts}",
            f"- Findings: {history.layer_summary.findings}",
            f"- Reports: {history.layer_summary.reports}",
            "",
            "## Findings",
        ]
        if findings:
            for finding in findings:
                lines.append(
                    f"- {finding.public_id} [{finding.severity}/{finding.status.value}] {finding.title} ({finding.target_ref})"
                )
        else:
            lines.append("- No findings recorded.")

        lines.extend(["", "## Artifacts"])
        if artifacts:
            for artifact in artifacts:
                lines.append(f"- {artifact.public_id} [{artifact.artifact_type}] {artifact.title}")
        else:
            lines.append("- No artifacts recorded.")

        lines.extend(["", "## Reports"])
        if reports:
            for report in reports:
                lines.append(f"- {report.public_id} [{report.report_type}] {report.title}")
        else:
            lines.append("- No reports recorded.")

        markdown = "\n".join(lines) + "\n"
        report = self.report_service.create_report(
            session_identifier=session.id,
            report_type="operator_report",
            title=f"Operator report for {session.public_id}",
            summary=f"Operator-readable report generated for session {session.public_id}.",
            artifact_identifiers=[artifact.public_id for artifact in artifacts],
            finding_identifiers=[finding.public_id for finding in findings],
            output_payload=markdown,
            output_extension=".md",
            metadata={"report_flow": "operator_report", "output_format": "markdown"},
        )
        return self._build_result(report, reused=False)

    def _find_reusable_report(self, session_id: str, *, report_type: str) -> Report | None:
        reports = self.report_service.list_reports(session_id, limit=None)
        for report in reports:
            if report.report_type == report_type:
                return report
        return None

    def _build_result(
        self,
        report: Report,
        *,
        reused: bool,
        fallback_artifact_ids: list[str] | None = None,
        fallback_finding_ids: list[str] | None = None,
    ) -> ReportFlowResult:
        artifact_links = self.report_service.list_artifact_links(report.id)
        finding_links = self.report_service.list_finding_links(report.id)
        linked_artifact_ids = [
            self.artifact_service.require_artifact(link.artifact_id).public_id
            for link in artifact_links
        ]
        linked_finding_ids = [
            self.finding_service.require_finding(link.finding_id).public_id
            for link in finding_links
        ]
        return ReportFlowResult(
            report=report,
            reused=reused,
            linked_artifact_ids=linked_artifact_ids or list(fallback_artifact_ids or []),
            linked_finding_ids=linked_finding_ids or list(fallback_finding_ids or []),
        )
