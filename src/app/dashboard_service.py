from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from agent.settings import Settings, get_settings
from models.artifact import Artifact
from models.finding import Finding
from models.job import Job
from models.session import Session, SessionMode
from models.session_event import SessionEvent
from models.scope_policy import ScopePolicy

from .scope_policy_service import ScopePolicyService
from .session_record_locator import SessionRecordLocator
from .session_scope import resolve_session_identifier
from .session_service import SessionService


@dataclass(frozen=True, slots=True)
class SessionDashboard:
    session: Session
    policy: ScopePolicy
    job_counts: dict[str, int]
    flagged_jobs: list[Job]
    finding_counts: dict[str, int]
    recent_findings: list[Finding]
    artifact_count: int
    recent_artifacts: list[Artifact]
    report_count: int
    event_counts: dict[str, int]
    recent_events: list[SessionEvent]

    @property
    def evidence_count(self) -> int:
        return self.artifact_count

    @property
    def recent_evidence(self) -> list[Artifact]:
        return self.recent_artifacts


class DashboardService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        scope_policy_service: ScopePolicyService,
        session_record_locator: SessionRecordLocator,
        settings: Settings,
    ) -> None:
        self.session_service = session_service
        self.scope_policy_service = scope_policy_service
        self.session_record_locator = session_record_locator
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "DashboardService":
        settings = settings or get_settings()
        return cls(
            session_service=SessionService.from_settings(settings),
            scope_policy_service=ScopePolicyService.from_settings(settings),
            session_record_locator=SessionRecordLocator.from_settings(settings),
            settings=settings,
        )

    def build_dashboard(self, session_identifier: str | None = None) -> SessionDashboard:
        session = self._resolve_session(session_identifier)
        policy = self.scope_policy_service.get_scope_policy_for_session(session.id)
        if policy is None:
            raise ValueError(f"Scope policy not found for session: {session.public_id or session.id}")
        jobs = self.session_record_locator.list_jobs(session.id, limit=None)
        findings = self.session_record_locator.list_findings(session.id, limit=None)
        artifacts = self.session_record_locator.list_artifacts(session.id, limit=None)
        reports = self.session_record_locator.list_reports(session.id, limit=None)
        events = self.session_record_locator.list_events(session.id, limit=None)

        job_counts = dict(Counter(job.status.value for job in jobs))
        finding_counts = dict(Counter(finding.status.value for finding in findings))
        event_counts = dict(Counter(event.event_type.value for event in events))

        flagged_statuses = {"failed", "timed_out", "blocked"}
        flagged_jobs = [job for job in jobs if job.status.value in flagged_statuses][:10]
        recent_findings = findings[:10]
        recent_artifacts = artifacts[:10]
        recent_events = events[:10]

        return SessionDashboard(
            session=session,
            policy=policy,
            job_counts=job_counts,
            flagged_jobs=flagged_jobs,
            finding_counts=finding_counts,
            recent_findings=recent_findings,
            artifact_count=len(artifacts),
            recent_artifacts=recent_artifacts,
            report_count=len(reports),
            event_counts=event_counts,
            recent_events=recent_events,
        )

    def _resolve_session(self, identifier: str | None) -> Session:
        if identifier:
            session_id = resolve_session_identifier(self.session_service, identifier)
            return self.session_service.require_session(session_id)

        sessions = self.session_service.list_sessions(mode=SessionMode.REDTEAM, limit=None)
        if not sessions:
            raise ValueError("No redteam sessions found for /dashboard.")
        return max(sessions, key=self._session_activity_key)

    def _session_activity_key(self, session: Session) -> tuple[int, datetime]:
        session_timestamps = [session.updated_at, session.created_at]
        runtime_timestamps: list[str] = []
        jobs = self.session_record_locator.list_jobs(session.id, limit=1)
        findings = self.session_record_locator.list_findings(session.id, limit=1)
        artifacts = self.session_record_locator.list_artifacts(session.id, limit=1)
        reports = self.session_record_locator.list_reports(session.id, limit=1)
        events = self.session_record_locator.list_events(session.id, limit=1)
        if jobs:
            runtime_timestamps.append(jobs[0].updated_at)
        if findings:
            runtime_timestamps.append(findings[0].updated_at)
        if artifacts:
            runtime_timestamps.append(artifacts[0].captured_at)
        if reports:
            runtime_timestamps.append(reports[0].created_at)
        if events:
            runtime_timestamps.append(events[0].created_at)
        timestamps = runtime_timestamps or session_timestamps
        return (1 if runtime_timestamps else 0, max(datetime.fromisoformat(timestamp) for timestamp in timestamps))
