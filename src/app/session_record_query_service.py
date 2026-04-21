from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agent.settings import Settings, get_settings
from models.artifact import Artifact
from models.finding import Finding
from models.job import Job, JobLogEntry
from models.report import Report
from models.run import Run, SessionLogEntry
from models.session import Session
from models.session_event import SessionEvent

from .artifact_service import ArtifactService
from .finding_service import FindingService
from .job_service import JobService
from .report_service import ReportService
from .run_service import RunService
from .session_event_service import SessionEventService
from .session_record_locator import SessionLayerSummary, SessionRecordLocator
from .session_service import SessionService


def _sort_key(timestamp: str | None) -> tuple[int, datetime]:
    if timestamp is None:
        return (1, datetime.min)
    return (0, datetime.fromisoformat(timestamp))


@dataclass(frozen=True, slots=True)
class SessionHistorySummaryView:
    layer_summary: SessionLayerSummary
    recent_runs: list[Run] = field(default_factory=list)
    recent_logs: list[SessionLogEntry] = field(default_factory=list)
    recent_jobs: list[Job] = field(default_factory=list)
    recent_events: list[SessionEvent] = field(default_factory=list)
    recent_artifacts: list[Artifact] = field(default_factory=list)
    recent_findings: list[Finding] = field(default_factory=list)
    recent_reports: list[Report] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ExecutionStepView:
    source_type: str
    occurred_at: str
    title: str
    detail: str
    status: str | None = None
    level: str | None = None
    run_public_id: str | None = None
    job_public_id: str | None = None


@dataclass(frozen=True, slots=True)
class FindingExplanationTraceView:
    finding: Finding
    linked_artifacts: list[Artifact] = field(default_factory=list)
    source_job: Job | None = None
    supporting_jobs: list[Job] = field(default_factory=list)
    source_job_logs: list[JobLogEntry] = field(default_factory=list)
    related_events: list[SessionEvent] = field(default_factory=list)
    related_run_ids: list[str] = field(default_factory=list)
    missing_segments: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing_segments


class SessionRecordQueryService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        locator: SessionRecordLocator,
        run_service: RunService,
        job_service: JobService,
        session_event_service: SessionEventService,
        artifact_service: ArtifactService,
        finding_service: FindingService,
        report_service: ReportService,
        settings: Settings,
    ) -> None:
        self.session_service = session_service
        self.locator = locator
        self.run_service = run_service
        self.job_service = job_service
        self.session_event_service = session_event_service
        self.artifact_service = artifact_service
        self.finding_service = finding_service
        self.report_service = report_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SessionRecordQueryService":
        settings = settings or get_settings()
        session_service = SessionService.from_settings(settings)
        return cls(
            session_service=session_service,
            locator=SessionRecordLocator.from_settings(settings),
            run_service=RunService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            session_event_service=SessionEventService.from_settings(settings),
            artifact_service=ArtifactService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            report_service=ReportService.from_settings(settings),
            settings=settings,
        )

    def get_history_summary(
        self,
        session_identifier: str,
        *,
        limit: int | None = 5,
    ) -> SessionHistorySummaryView:
        session = self._require_session(session_identifier)
        preview_limit = limit or 5
        return SessionHistorySummaryView(
            layer_summary=self.locator.get_layer_summary(session.id),
            recent_runs=self.locator.list_runs(session.id, limit=preview_limit),
            recent_logs=self.locator.list_logs(session.id, limit=preview_limit),
            recent_jobs=self.locator.list_jobs(session.id, limit=preview_limit),
            recent_events=self.locator.list_events(session.id, limit=preview_limit),
            recent_artifacts=self.locator.list_artifacts(session.id, limit=preview_limit),
            recent_findings=self.locator.list_findings(session.id, limit=preview_limit),
            recent_reports=self.locator.list_reports(session.id, limit=preview_limit),
        )

    def list_execution_steps(
        self,
        session_identifier: str,
        limit: int | None = 50,
    ) -> list[ExecutionStepView]:
        session = self._require_session(session_identifier)
        effective_limit = limit or 50
        runs = self.run_service.list_runs(session.id, limit=effective_limit)
        logs = self.run_service.list_logs(session.id, limit=effective_limit)
        jobs = self.job_service.list_jobs(session.id, limit=effective_limit)
        events = self.session_event_service.list_events(session.id, limit=effective_limit)

        run_labels = {run.id: run.public_id for run in runs}
        job_labels = {job.id: job.public_id for job in jobs}

        steps: list[ExecutionStepView] = []
        for run in runs:
            steps.append(
                ExecutionStepView(
                    source_type="run",
                    occurred_at=run.finished_at or run.started_at,
                    title=f"Run {run.status.value}",
                    detail=self._describe_run(run),
                    status=run.status.value,
                    run_public_id=run.public_id,
                )
            )

        for log in logs:
            steps.append(
                ExecutionStepView(
                    source_type="log",
                    occurred_at=log.created_at,
                    title=log.message,
                    detail=self._describe_log(log),
                    level=log.level.value,
                    run_public_id=run_labels.get(log.run_id) if log.run_id else None,
                )
            )

        for job in jobs:
            steps.append(
                ExecutionStepView(
                    source_type="job",
                    occurred_at=self._job_timestamp(job),
                    title=f"Job {job.status.value}: {job.job_type}",
                    detail=job.target_ref,
                    status=job.status.value,
                    job_public_id=job.public_id,
                )
            )

        for event in events:
            steps.append(
                ExecutionStepView(
                    source_type="event",
                    occurred_at=event.created_at,
                    title=event.event_type.value,
                    detail=event.message or event.target_ref,
                    level=event.level.value,
                    job_public_id=job_labels.get(event.job_id) if event.job_id else None,
                )
            )

        steps.sort(key=lambda item: _sort_key(item.occurred_at), reverse=True)
        return steps[:effective_limit]

    def list_artifacts(
        self,
        session_identifier: str,
        *,
        limit: int | None = 50,
        artifact_type: str | None = None,
        artifact_identifier: str | None = None,
    ) -> list[Artifact]:
        session = self._require_session(session_identifier)
        artifacts = self._resolve_artifacts(session=session, limit=limit, artifact_identifier=artifact_identifier)
        if artifact_type is not None:
            artifacts = [artifact for artifact in artifacts if artifact.artifact_type == artifact_type]
        return artifacts

    def list_findings(
        self,
        session_identifier: str,
        *,
        limit: int | None = 50,
        severity: str | None = None,
        status: str | None = None,
        finding_identifier: str | None = None,
    ) -> list[Finding]:
        session = self._require_session(session_identifier)
        findings = self._resolve_findings(session=session, limit=limit, finding_identifier=finding_identifier)
        if severity is not None:
            findings = [finding for finding in findings if finding.severity == severity]
        if status is not None:
            findings = [finding for finding in findings if finding.status.value == status]
        return findings

    def list_reports(
        self,
        session_identifier: str,
        *,
        limit: int | None = 50,
        report_type: str | None = None,
        report_identifier: str | None = None,
    ) -> list[Report]:
        session = self._require_session(session_identifier)
        reports = self._resolve_reports(session=session, limit=limit, report_identifier=report_identifier)
        if report_type is not None:
            reports = [report for report in reports if report.report_type == report_type]
        return reports

    def explain_finding(
        self,
        session_identifier: str,
        finding_identifier: str,
    ) -> FindingExplanationTraceView:
        session = self._require_session(session_identifier)
        finding = self.finding_service.require_finding(finding_identifier)
        if finding.session_id != session.id:
            raise ValueError(
                f"Finding {finding_identifier} does not belong to session {session.public_id}."
            )

        artifact_links = self.finding_service.list_artifact_links_for_finding(finding.id)
        linked_artifacts = [
            self.artifact_service.require_artifact(link.artifact_id)
            for link in artifact_links
        ]

        supporting_job_ids = {job_id for job_id in [finding.source_job_id] if job_id}
        supporting_job_ids.update(
            artifact.source_job_id
            for artifact in linked_artifacts
            if artifact.source_job_id is not None
        )
        supporting_jobs = [
            job
            for job_id in supporting_job_ids
            for job in [self.job_service.get_job(job_id)]
            if job is not None
        ]
        supporting_jobs.sort(key=lambda item: _sort_key(item.created_at), reverse=True)

        source_job = None
        if finding.source_job_id is not None:
            source_job = self.job_service.get_job(finding.source_job_id)

        source_job_logs: list[JobLogEntry] = []
        if source_job is not None:
            source_job_logs = self.job_service.list_logs(source_job.id, limit=20)

        related_events = [
            event
            for event in self.session_event_service.list_events(session.id, limit=200)
            if event.job_id in supporting_job_ids
        ]
        related_events.sort(key=lambda item: _sort_key(item.created_at), reverse=True)

        related_run_ids = sorted(
            {
                str(event.payload.get("run_id")).strip()
                for event in related_events
                if event.payload.get("run_id")
            }
        )

        missing_segments: list[str] = []
        if not linked_artifacts:
            missing_segments.append("linked_artifacts")
        if source_job is None:
            missing_segments.append("source_job")
        if not related_events:
            missing_segments.append("execution_events")
        if not related_run_ids:
            missing_segments.append("source_run")

        return FindingExplanationTraceView(
            finding=finding,
            linked_artifacts=linked_artifacts,
            source_job=source_job,
            supporting_jobs=supporting_jobs,
            source_job_logs=source_job_logs,
            related_events=related_events,
            related_run_ids=related_run_ids,
            missing_segments=missing_segments,
        )

    def _require_session(self, session_identifier: str) -> Session:
        return self.session_service.require_session(session_identifier)

    def _resolve_artifacts(
        self,
        *,
        session: Session,
        limit: int | None,
        artifact_identifier: str | None,
    ) -> list[Artifact]:
        if artifact_identifier is not None:
            artifact = self.artifact_service.require_artifact(artifact_identifier)
            if artifact.session_id != session.id:
                raise ValueError(
                    f"Artifact {artifact_identifier} does not belong to session {session.public_id}."
                )
            return [artifact]
        return self.locator.list_artifacts(session.id, limit=limit)

    def _resolve_findings(
        self,
        *,
        session: Session,
        limit: int | None,
        finding_identifier: str | None,
    ) -> list[Finding]:
        if finding_identifier is not None:
            finding = self.finding_service.require_finding(finding_identifier)
            if finding.session_id != session.id:
                raise ValueError(
                    f"Finding {finding_identifier} does not belong to session {session.public_id}."
                )
            return [finding]
        return self.locator.list_findings(session.id, limit=limit)

    def _resolve_reports(
        self,
        *,
        session: Session,
        limit: int | None,
        report_identifier: str | None,
    ) -> list[Report]:
        if report_identifier is not None:
            report = self.report_service.require_report(report_identifier)
            if report.session_id != session.id:
                raise ValueError(
                    f"Report {report_identifier} does not belong to session {session.public_id}."
                )
            return [report]
        return self.locator.list_reports(session.id, limit=limit)

    def _describe_run(self, run: Run) -> str:
        details = [f"steps={run.step_count}"]
        if run.effective_skill_name:
            details.append(f"skill={run.effective_skill_name}")
        if run.failure_kind:
            details.append(f"failure={run.failure_kind}")
        if run.last_error:
            details.append(f"error={run.last_error}")
        return " | ".join(details)

    def _describe_log(self, log: SessionLogEntry) -> str:
        payload = log.payload or {}
        preferred_keys = (
            "tool_name",
            "capability",
            "failure_kind",
            "skill_name",
            "args_summary",
            "result_summary",
            "error",
            "reason",
        )
        parts = [
            f"{key}={payload[key]}"
            for key in preferred_keys
            if payload.get(key) not in (None, "", [])
        ]
        return " | ".join(parts) if parts else "-"

    def _job_timestamp(self, job: Job) -> str:
        return (
            job.finished_at
            or job.started_at
            or job.queued_at
            or job.updated_at
            or job.created_at
        )
