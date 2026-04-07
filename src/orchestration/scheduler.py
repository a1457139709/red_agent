from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings, get_settings
from models.run import utc_now_iso

from .job_service import JobOrchestrationService


@dataclass(frozen=True, slots=True)
class SchedulerPassResult:
    recovered_count: int = 0
    cancelled_count: int = 0
    blocked_count: int = 0
    queued_count: int = 0

    @property
    def total_changes(self) -> int:
        return self.recovered_count + self.cancelled_count + self.blocked_count + self.queued_count


class Scheduler:
    def __init__(
        self,
        *,
        job_service: JobOrchestrationService,
        settings: Settings,
    ) -> None:
        self.job_service = job_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "Scheduler":
        settings = settings or get_settings()
        return cls(
            job_service=JobOrchestrationService.from_settings(settings),
            settings=settings,
        )

    def run_once(
        self,
        *,
        operation_identifier: str | None = None,
        now: str | None = None,
    ) -> SchedulerPassResult:
        timestamp = now or utc_now_iso()
        recovered = self.job_service.recover_stale_leases(operation_identifier, now=timestamp)
        cancelled = self.job_service.cancel_requested_jobs(operation_identifier, now=timestamp)
        blocked = self.job_service.block_jobs_with_failed_dependencies(operation_identifier, now=timestamp)
        queued = self.job_service.enqueue_ready_jobs(operation_identifier, now=timestamp)
        return SchedulerPassResult(
            recovered_count=len(recovered),
            cancelled_count=len(cancelled),
            blocked_count=len(blocked),
            queued_count=len(queued),
        )
