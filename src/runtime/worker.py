from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Thread

from agent.settings import Settings, get_settings
from app.scoped_execution_service import ConfirmCallback
from app.security_tool_execution_service import SecurityToolExecutionService
from models.job import JobStatus
from models.run import utc_now_iso
from orchestration.job_service import JobOrchestrationService
from orchestration.scheduler import Scheduler

from .leases import DEFAULT_JOB_LEASE_SECONDS, new_worker_id


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    worker_id: str
    job_public_id: str | None
    status: str
    message: str


@dataclass(frozen=True, slots=True)
class WorkerDrainResult:
    worker_id: str
    scheduler_passes: int
    run_results: list[WorkerRunResult] = field(default_factory=list)


class WorkerRuntime:
    def __init__(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        scheduler: Scheduler,
        job_service: JobOrchestrationService,
        execution_service: SecurityToolExecutionService,
        settings: Settings,
    ) -> None:
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.scheduler = scheduler
        self.job_service = job_service
        self.execution_service = execution_service
        self.settings = settings

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        worker_id: str | None = None,
        lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
    ) -> "WorkerRuntime":
        settings = settings or get_settings()
        return cls(
            worker_id=worker_id or new_worker_id(),
            lease_seconds=lease_seconds,
            scheduler=Scheduler.from_settings(settings),
            job_service=JobOrchestrationService.from_settings(settings),
            execution_service=SecurityToolExecutionService.from_settings(settings),
            settings=settings,
        )

    def run_once(
        self,
        *,
        confirm: ConfirmCallback = None,
        now: str | None = None,
    ) -> WorkerRunResult:
        timestamp = now or utc_now_iso()
        job = self.job_service.claim_next_queued_job(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            now=timestamp,
        )
        if job is None:
            return WorkerRunResult(
                worker_id=self.worker_id,
                job_public_id=None,
                status="no_work",
                message="No queued jobs were available.",
            )

        if job.lease_token is None:
            raise ValueError("Claimed job is missing a lease token.")

        self.job_service.heartbeat(
            job_identifier=job.id,
            lease_token=job.lease_token,
            lease_seconds=self.lease_seconds,
            now=timestamp,
        )

        cancelled = self.job_service.cancel_running_if_requested(
            job_identifier=job.id,
            lease_token=job.lease_token,
            now=timestamp,
        )
        if cancelled is not None:
            return WorkerRunResult(
                worker_id=self.worker_id,
                job_public_id=cancelled.public_id,
                status="cancelled",
                message=cancelled.last_error or "Job cancelled before execution.",
            )

        stop_heartbeat = Event()
        heartbeat_thread = self._start_heartbeat_loop(
            job_identifier=job.id,
            lease_token=job.lease_token,
            stop_event=stop_heartbeat,
        )
        try:
            execution_result = self.execution_service.execute_job(
                job_identifier=job.id,
                confirm=confirm,
            )
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=self._heartbeat_interval_seconds() + 0.5)

        self.job_service.heartbeat(
            job_identifier=job.id,
            lease_token=job.lease_token,
            lease_seconds=self.lease_seconds,
            now=utc_now_iso(),
        )
        resolution = self.job_service.record_attempt_outcome(
            job_identifier=job.id,
            lease_token=job.lease_token,
            outcome=execution_result.status,
            message=execution_result.message,
            now=utc_now_iso(),
        )

        return WorkerRunResult(
            worker_id=self.worker_id,
            job_public_id=resolution.job.public_id,
            status=_resolution_status(resolution.job.status, requeued=resolution.requeued),
            message=resolution.job.last_error or execution_result.message,
        )

    def drain(
        self,
        *,
        confirm: ConfirmCallback = None,
        max_iterations: int = 100,
    ) -> WorkerDrainResult:
        scheduler_passes = 0
        run_results: list[WorkerRunResult] = []
        for _ in range(max_iterations):
            scheduler_result = self.scheduler.run_once()
            scheduler_passes += 1
            run_result = self.run_once(confirm=confirm)
            if run_result.status != "no_work":
                run_results.append(run_result)
            if scheduler_result.total_changes == 0 and run_result.status == "no_work":
                break
        return WorkerDrainResult(
            worker_id=self.worker_id,
            scheduler_passes=scheduler_passes,
            run_results=run_results,
        )

    def _start_heartbeat_loop(
        self,
        *,
        job_identifier: str,
        lease_token: str,
        stop_event: Event,
    ) -> Thread:
        thread = Thread(
            target=self._heartbeat_loop,
            kwargs={
                "job_identifier": job_identifier,
                "lease_token": lease_token,
                "stop_event": stop_event,
            },
            daemon=True,
        )
        thread.start()
        return thread

    def _heartbeat_loop(
        self,
        *,
        job_identifier: str,
        lease_token: str,
        stop_event: Event,
    ) -> None:
        interval_seconds = self._heartbeat_interval_seconds()
        while not stop_event.wait(interval_seconds):
            refreshed = self.job_service.heartbeat(
                job_identifier=job_identifier,
                lease_token=lease_token,
                lease_seconds=self.lease_seconds,
                now=utc_now_iso(),
            )
            if refreshed is None:
                return

    def _heartbeat_interval_seconds(self) -> float:
        return max(0.1, self.lease_seconds / 3)


def _resolution_status(status: JobStatus, *, requeued: bool) -> str:
    if requeued:
        return "requeued"
    return status.value
