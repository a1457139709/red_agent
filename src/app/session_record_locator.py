from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings, get_settings
from models.artifact import Artifact
from models.checkpoint import CheckpointSummary
from models.finding import Finding
from models.job import Job
from models.memory import MemoryEntry
from models.report import Report
from models.run import Run, SessionLogEntry
from models.session_event import SessionEvent

from .artifact_service import ArtifactService
from .checkpoint_service import CheckpointService
from .finding_service import FindingService
from .job_service import JobService
from .memory_service import MemoryService
from .report_service import ReportService
from .run_service import RunService
from .session_event_service import SessionEventService


@dataclass(frozen=True, slots=True)
class SessionLayerSummary:
    runs: int
    logs: int
    checkpoints: int
    jobs: int
    events: int
    memory_entries: int
    artifacts: int
    findings: int
    reports: int


class SessionRecordLocator:
    def __init__(
        self,
        *,
        run_service: RunService,
        checkpoint_service: CheckpointService,
        job_service: JobService,
        session_event_service: SessionEventService,
        memory_service: MemoryService,
        artifact_service: ArtifactService,
        finding_service: FindingService,
        report_service: ReportService,
        settings: Settings,
    ) -> None:
        self.run_service = run_service
        self.checkpoint_service = checkpoint_service
        self.job_service = job_service
        self.session_event_service = session_event_service
        self.memory_service = memory_service
        self.artifact_service = artifact_service
        self.finding_service = finding_service
        self.report_service = report_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SessionRecordLocator":
        settings = settings or get_settings()
        return cls(
            run_service=RunService.from_settings(settings),
            checkpoint_service=CheckpointService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            session_event_service=SessionEventService.from_settings(settings),
            memory_service=MemoryService.from_settings(settings),
            artifact_service=ArtifactService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            report_service=ReportService.from_settings(settings),
            settings=settings,
        )

    def get_layer_summary(self, session_identifier: str) -> SessionLayerSummary:
        runs = self.list_runs(session_identifier, limit=None)
        logs = self.list_logs(session_identifier, limit=None)
        checkpoints = self.list_checkpoints(session_identifier, limit=None)
        jobs = self.list_jobs(session_identifier, limit=None)
        events = self.list_events(session_identifier, limit=None)
        memory_entries = self.list_memory_entries(session_identifier, limit=None)
        artifacts = self.list_artifacts(session_identifier, limit=None)
        findings = self.list_findings(session_identifier, limit=None)
        reports = self.list_reports(session_identifier, limit=None)
        return SessionLayerSummary(
            runs=len(runs),
            logs=len(logs),
            checkpoints=len(checkpoints),
            jobs=len(jobs),
            events=len(events),
            memory_entries=len(memory_entries),
            artifacts=len(artifacts),
            findings=len(findings),
            reports=len(reports),
        )

    def list_runs(self, session_identifier: str, *, limit: int | None = 50) -> list[Run]:
        return self.run_service.list_runs(session_identifier, limit=limit or 10_000)

    def list_logs(self, session_identifier: str, *, limit: int | None = 50) -> list[SessionLogEntry]:
        return self.run_service.list_logs(session_identifier, limit=limit or 10_000)

    def list_checkpoints(self, session_identifier: str, *, limit: int | None = 50) -> list[CheckpointSummary]:
        return self.checkpoint_service.list_checkpoints(session_identifier, limit=limit or 10_000)

    def list_jobs(self, session_identifier: str, *, limit: int | None = 50) -> list[Job]:
        return self.job_service.list_jobs(session_identifier, limit=limit)

    def list_events(self, session_identifier: str, *, limit: int | None = 50) -> list[SessionEvent]:
        return self.session_event_service.list_events(session_identifier, limit=limit)

    def list_memory_entries(self, session_identifier: str, *, limit: int | None = 50) -> list[MemoryEntry]:
        return self.memory_service.list_memory_entries(session_identifier, limit=limit)

    def list_artifacts(self, session_identifier: str, *, limit: int | None = 50) -> list[Artifact]:
        return self.artifact_service.list_artifacts(session_identifier, limit=limit)

    def list_findings(self, session_identifier: str, *, limit: int | None = 50) -> list[Finding]:
        return self.finding_service.list_findings(session_identifier, limit=limit)

    def list_reports(self, session_identifier: str, *, limit: int | None = 50) -> list[Report]:
        return self.report_service.list_reports(session_identifier, limit=limit)
