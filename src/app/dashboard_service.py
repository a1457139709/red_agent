from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from agent.settings import Settings, get_settings
from models.evidence import Evidence
from models.finding import Finding
from models.job import Job
from models.operation import Operation
from models.operation_event import OperationEvent, OperationEventType
from models.scope_policy import ScopePolicy

from .evidence_service import EvidenceService
from .finding_service import FindingService
from .job_service import JobService
from .operation_event_service import OperationEventService
from .operation_service import OperationService


@dataclass(frozen=True, slots=True)
class OperationDashboard:
    operation: Operation
    policy: ScopePolicy
    job_counts: dict[str, int]
    flagged_jobs: list[Job]
    finding_counts: dict[str, int]
    recent_findings: list[Finding]
    evidence_count: int
    recent_evidence: list[Evidence]
    event_counts: dict[str, int]
    recent_events: list[OperationEvent]


class DashboardService:
    def __init__(
        self,
        *,
        operation_service: OperationService,
        job_service: JobService,
        finding_service: FindingService,
        evidence_service: EvidenceService,
        operation_event_service: OperationEventService,
        settings: Settings,
    ) -> None:
        self.operation_service = operation_service
        self.job_service = job_service
        self.finding_service = finding_service
        self.evidence_service = evidence_service
        self.operation_event_service = operation_event_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "DashboardService":
        settings = settings or get_settings()
        return cls(
            operation_service=OperationService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            evidence_service=EvidenceService.from_settings(settings),
            operation_event_service=OperationEventService.from_settings(settings),
            settings=settings,
        )

    def build_dashboard(self, operation_identifier: str | None = None) -> OperationDashboard:
        operation = self._resolve_operation(operation_identifier)
        policy = self.operation_service.require_scope_policy(operation.id)
        jobs = self.job_service.list_jobs(operation.id, limit=None)
        findings = self.finding_service.list_findings(operation.id, limit=None)
        evidence = self.evidence_service.list_evidence(operation.id, limit=None)
        events = self.operation_event_service.list_events(operation.id, limit=None)

        job_counts = dict(Counter(job.status.value for job in jobs))
        finding_counts = dict(Counter(finding.status.value for finding in findings))
        event_counts = dict(Counter(event.event_type.value for event in events))

        flagged_statuses = {"failed", "timed_out", "blocked"}
        flagged_jobs = [job for job in jobs if job.status.value in flagged_statuses][:10]
        recent_findings = findings[:10]
        recent_evidence = evidence[:10]
        recent_events = events[:10]

        return OperationDashboard(
            operation=operation,
            policy=policy,
            job_counts=job_counts,
            flagged_jobs=flagged_jobs,
            finding_counts=finding_counts,
            recent_findings=recent_findings,
            evidence_count=len(evidence),
            recent_evidence=recent_evidence,
            event_counts={
                OperationEventType.ADMISSION_DENIED.value: event_counts.get(
                    OperationEventType.ADMISSION_DENIED.value,
                    0,
                ),
                OperationEventType.CONFIRMATION_DENIED.value: event_counts.get(
                    OperationEventType.CONFIRMATION_DENIED.value,
                    0,
                ),
                OperationEventType.EXECUTION_FAILED.value: event_counts.get(
                    OperationEventType.EXECUTION_FAILED.value,
                    0,
                ),
            },
            recent_events=recent_events,
        )

    def _resolve_operation(self, operation_identifier: str | None) -> Operation:
        if operation_identifier:
            return self.operation_service.require_operation(operation_identifier)

        operations = self.operation_service.list_operations(limit=1)
        if not operations:
            raise ValueError("No operations found for /dashboard.")
        return operations[0]
