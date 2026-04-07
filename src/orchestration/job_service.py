from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from agent.settings import Settings, get_settings
from app.job_service import JobService as AppJobService
from app.operation_service import OperationService
from models.job import Job, JobLogLevel, JobStatus
from models.operation import OperationStatus
from models.run import utc_now_iso
from runtime.leases import DEFAULT_JOB_LEASE_SECONDS, lease_deadline, new_lease_token
from storage.repositories.jobs import JobRepository
from storage.sqlite import SQLiteStorage


RETRY_BACKOFF_SECONDS = 5
RUNNABLE_OPERATION_STATUSES = frozenset({OperationStatus.READY, OperationStatus.RUNNING})
DEPENDENCY_FAILURE_STATUSES = frozenset(
    {
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
        JobStatus.BLOCKED,
        JobStatus.CANCELLED,
    }
)
TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
        JobStatus.BLOCKED,
        JobStatus.CANCELLED,
    }
)


@dataclass(frozen=True, slots=True)
class AttemptResolution:
    job: Job
    final_status: JobStatus
    requeued: bool
    cancelled: bool


class JobOrchestrationService:
    def __init__(
        self,
        *,
        repository: JobRepository,
        job_service: AppJobService,
        operation_service: OperationService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.job_service = job_service
        self.operation_service = operation_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "JobOrchestrationService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            repository=JobRepository(storage),
            job_service=AppJobService.from_settings(settings),
            operation_service=OperationService.from_settings(settings),
            settings=settings,
        )

    def enqueue_ready_jobs(
        self,
        operation_identifier: str | None = None,
        *,
        now: str | None = None,
    ) -> list[Job]:
        timestamp = now or utc_now_iso()
        updated_jobs: list[Job] = []
        for operation_jobs in self._iter_operation_jobs(operation_identifier):
            if not self._operation_is_runnable(operation_jobs[0].operation_id):
                continue
            job_map = {job.id: job for job in operation_jobs}
            for job in operation_jobs:
                if job.status != JobStatus.PENDING or job.cancel_requested_at is not None:
                    continue
                dependencies = self._dependency_jobs(job, job_map)
                if dependencies is None:
                    continue
                if any(dependency.status in DEPENDENCY_FAILURE_STATUSES for dependency in dependencies):
                    continue
                if not all(dependency.status == JobStatus.SUCCEEDED for dependency in dependencies):
                    continue
                job.status = JobStatus.QUEUED
                job.queued_at = timestamp
                job.retry_after = None
                job.updated_at = timestamp
                self.job_service.save_job(job)
                self.job_service.write_log(
                    job_identifier=job.id,
                    level=job_log_level(JobStatus.QUEUED),
                    message="job_queued",
                    payload={"reason": "dependencies_satisfied"},
                )
                updated_jobs.append(job)
        return updated_jobs

    def request_cancellation(
        self,
        job_identifier: str,
        *,
        reason: str = "Operator requested cancellation.",
        now: str | None = None,
    ) -> Job:
        timestamp = now or utc_now_iso()
        job = self.job_service.require_job(job_identifier)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        job.cancel_requested_at = timestamp
        job.cancel_reason = reason
        job.updated_at = timestamp
        self.job_service.save_job(job)
        self.job_service.write_log(
            job_identifier=job.id,
            level=job_log_level(job.status),
            message="job_cancellation_requested",
            payload={"reason": reason},
        )
        return job

    def cancel_requested_jobs(
        self,
        operation_identifier: str | None = None,
        *,
        now: str | None = None,
    ) -> list[Job]:
        timestamp = now or utc_now_iso()
        cancelled_jobs: list[Job] = []
        candidate_statuses = {JobStatus.PENDING, JobStatus.QUEUED}
        for job in self._iter_candidate_jobs(operation_identifier, statuses=candidate_statuses):
            if job.cancel_requested_at is None:
                continue
            self._clear_lease(job)
            job.status = JobStatus.CANCELLED
            job.finished_at = timestamp
            job.last_error = job.cancel_reason or "Job cancellation was requested."
            job.retry_after = None
            job.updated_at = timestamp
            self.job_service.save_job(job)
            self.job_service.write_log(
                job_identifier=job.id,
                level=job_log_level(job.status),
                message="job_cancelled",
                payload={"reason": job.cancel_reason},
            )
            cancelled_jobs.append(job)
        return cancelled_jobs

    def block_jobs_with_failed_dependencies(
        self,
        operation_identifier: str | None = None,
        *,
        now: str | None = None,
    ) -> list[Job]:
        timestamp = now or utc_now_iso()
        blocked_jobs: list[Job] = []
        for operation_jobs in self._iter_operation_jobs(operation_identifier):
            job_map = {job.id: job for job in operation_jobs}
            for job in operation_jobs:
                if job.status not in {JobStatus.PENDING, JobStatus.QUEUED}:
                    continue
                dependencies = self._dependency_jobs(job, job_map)
                if dependencies is None:
                    message = "One or more dependency jobs could not be resolved."
                else:
                    failed_dependencies = [
                        dependency
                        for dependency in dependencies
                        if dependency.status in DEPENDENCY_FAILURE_STATUSES
                    ]
                    if not failed_dependencies:
                        continue
                    failed_refs = ", ".join(
                        dependency.public_id or dependency.id[:8] for dependency in failed_dependencies
                    )
                    message = f"Dependencies entered terminal failure states: {failed_refs}."
                self._clear_lease(job)
                job.status = JobStatus.BLOCKED
                job.finished_at = timestamp
                job.last_error = message
                job.retry_after = None
                job.updated_at = timestamp
                self.job_service.save_job(job)
                self.job_service.write_log(
                    job_identifier=job.id,
                    level=job_log_level(job.status),
                    message="job_blocked",
                    payload={"reason": message},
                )
                blocked_jobs.append(job)
        return blocked_jobs

    def recover_stale_leases(
        self,
        operation_identifier: str | None = None,
        *,
        now: str | None = None,
    ) -> list[AttemptResolution]:
        timestamp = now or utc_now_iso()
        operation_id: str | None = None
        if operation_identifier is not None:
            operation_id = self.operation_service.require_operation(operation_identifier).id
        recovered: list[AttemptResolution] = []
        for job in self.repository.list_stale_leases(now=timestamp, operation_id=operation_id):
            if job.cancel_requested_at is not None:
                cancelled_job = self._cancel_running_job(
                    job=job,
                    reason=job.cancel_reason or "Job cancellation was requested after lease recovery.",
                    now=timestamp,
                )
                recovered.append(
                    AttemptResolution(
                        job=cancelled_job,
                        final_status=cancelled_job.status,
                        requeued=False,
                        cancelled=True,
                    )
                )
                continue

            message = "Worker lease expired before the job completed."
            if job.retry_count < job.retry_limit:
                job.retry_count += 1
                self._requeue_job(job, message=message, now=timestamp)
                self.job_service.write_log(
                    job_identifier=job.id,
                    level=job_log_level(job.status),
                    message="job_requeued_after_stale_lease",
                    payload={"retry_count": job.retry_count, "reason": message},
                )
                recovered.append(
                    AttemptResolution(
                        job=job,
                        final_status=job.status,
                        requeued=True,
                        cancelled=False,
                    )
                )
                continue

            self._clear_lease(job)
            job.status = JobStatus.FAILED
            job.finished_at = timestamp
            job.last_error = message
            job.retry_after = None
            job.updated_at = timestamp
            self.job_service.save_job(job)
            self.job_service.write_log(
                job_identifier=job.id,
                level=job_log_level(job.status),
                message="job_failed_after_stale_lease",
                payload={"retry_count": job.retry_count, "reason": message},
            )
            recovered.append(
                AttemptResolution(
                    job=job,
                    final_status=job.status,
                    requeued=False,
                    cancelled=False,
                )
            )
        return recovered

    def claim_next_queued_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
        now: str | None = None,
    ) -> Job | None:
        timestamp = now or utc_now_iso()
        job = self.repository.claim_next_queued_job(
            worker_id=worker_id,
            lease_token=new_lease_token(),
            now=timestamp,
            lease_expires_at=lease_deadline(now=timestamp, lease_seconds=lease_seconds),
        )
        if job is None:
            return None
        self.job_service.write_log(
            job_identifier=job.id,
            level=job_log_level(job.status),
            message="job_leased",
            payload={"worker_id": worker_id, "lease_token": job.lease_token},
        )
        return job

    def heartbeat(
        self,
        *,
        job_identifier: str,
        lease_token: str,
        lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
        now: str | None = None,
    ) -> Job | None:
        timestamp = now or utc_now_iso()
        return self.repository.refresh_lease(
            job_id=self.job_service.require_job(job_identifier).id,
            lease_token=lease_token,
            now=timestamp,
            lease_expires_at=lease_deadline(now=timestamp, lease_seconds=lease_seconds),
        )

    def cancel_running_if_requested(
        self,
        *,
        job_identifier: str,
        lease_token: str,
        now: str | None = None,
    ) -> Job | None:
        timestamp = now or utc_now_iso()
        job = self.job_service.require_job(job_identifier)
        if job.lease_token != lease_token or job.status != JobStatus.RUNNING:
            return None
        if job.cancel_requested_at is None:
            return None
        return self._cancel_running_job(
            job=job,
            reason=job.cancel_reason or "Job cancellation was requested.",
            now=timestamp,
        )

    def record_attempt_outcome(
        self,
        *,
        job_identifier: str,
        lease_token: str,
        outcome: str,
        message: str,
        now: str | None = None,
    ) -> AttemptResolution:
        timestamp = now or utc_now_iso()
        job = self.job_service.require_job(job_identifier)
        if job.lease_token != lease_token or job.status != JobStatus.RUNNING:
            raise ValueError("Job is no longer owned by the active worker lease.")

        if job.cancel_requested_at is not None:
            cancelled_job = self._cancel_running_job(
                job=job,
                reason=job.cancel_reason or "Job cancellation was requested.",
                now=timestamp,
            )
            return AttemptResolution(
                job=cancelled_job,
                final_status=cancelled_job.status,
                requeued=False,
                cancelled=True,
            )

        if outcome == "succeeded":
            self._clear_lease(job)
            job.status = JobStatus.SUCCEEDED
            job.finished_at = timestamp
            job.last_error = None
            job.retry_after = None
            job.updated_at = timestamp
            self.job_service.save_job(job)
            self.job_service.write_log(
                job_identifier=job.id,
                level=job_log_level(job.status),
                message="job_succeeded",
                payload={},
            )
            return AttemptResolution(
                job=job,
                final_status=job.status,
                requeued=False,
                cancelled=False,
            )

        if outcome == "blocked":
            self._clear_lease(job)
            job.status = JobStatus.BLOCKED
            job.finished_at = timestamp
            job.last_error = message
            job.retry_after = None
            job.updated_at = timestamp
            self.job_service.save_job(job)
            self.job_service.write_log(
                job_identifier=job.id,
                level=job_log_level(job.status),
                message="job_blocked",
                payload={"reason": message},
            )
            return AttemptResolution(
                job=job,
                final_status=job.status,
                requeued=False,
                cancelled=False,
            )

        terminal_status = JobStatus.TIMED_OUT if outcome == "timed_out" else JobStatus.FAILED
        if job.retry_count < job.retry_limit:
            job.retry_count += 1
            self._requeue_job(job, message=message, now=timestamp)
            self.job_service.write_log(
                job_identifier=job.id,
                level=job_log_level(job.status),
                message="job_requeued",
                payload={"retry_count": job.retry_count, "reason": message, "outcome": outcome},
            )
            return AttemptResolution(
                job=job,
                final_status=job.status,
                requeued=True,
                cancelled=False,
            )

        self._clear_lease(job)
        job.status = terminal_status
        job.finished_at = timestamp
        job.last_error = message
        job.retry_after = None
        job.updated_at = timestamp
        self.job_service.save_job(job)
        self.job_service.write_log(
            job_identifier=job.id,
            level=job_log_level(job.status),
            message="job_failed" if terminal_status == JobStatus.FAILED else "job_timed_out",
            payload={"reason": message, "retry_count": job.retry_count},
        )
        return AttemptResolution(
            job=job,
            final_status=job.status,
            requeued=False,
            cancelled=False,
        )

    def _cancel_running_job(
        self,
        *,
        job: Job,
        reason: str,
        now: str,
    ) -> Job:
        self._clear_lease(job)
        job.status = JobStatus.CANCELLED
        job.finished_at = now
        job.last_error = reason
        job.retry_after = None
        job.updated_at = now
        self.job_service.save_job(job)
        self.job_service.write_log(
            job_identifier=job.id,
            level=job_log_level(job.status),
            message="job_cancelled",
            payload={"reason": reason},
        )
        return job

    def _requeue_job(self, job: Job, *, message: str, now: str) -> None:
        self._clear_lease(job)
        job.status = JobStatus.QUEUED
        job.queued_at = now
        job.started_at = None
        job.finished_at = None
        job.last_error = message
        job.retry_after = (datetime.fromisoformat(now) + timedelta(seconds=RETRY_BACKOFF_SECONDS)).isoformat()
        job.updated_at = now
        self.job_service.save_job(job)

    def _clear_lease(self, job: Job) -> None:
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.last_heartbeat_at = None

    def _iter_candidate_jobs(
        self,
        operation_identifier: str | None,
        *,
        statuses: set[JobStatus],
    ) -> list[Job]:
        jobs = self.repository.list_by_statuses(statuses)
        if operation_identifier is None:
            return jobs
        operation = self.operation_service.require_operation(operation_identifier)
        return [job for job in jobs if job.operation_id == operation.id]

    def _iter_operation_jobs(self, operation_identifier: str | None) -> list[list[Job]]:
        grouped: dict[str, list[Job]] = defaultdict(list)
        if operation_identifier is not None:
            operation = self.operation_service.require_operation(operation_identifier)
            jobs = self.repository.list(operation.id, limit=None)
            return [jobs] if jobs else []
        for job in self.repository.list_by_statuses(
            {
                JobStatus.PENDING,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.TIMED_OUT,
                JobStatus.BLOCKED,
                JobStatus.CANCELLED,
            }
        ):
            grouped[job.operation_id].append(job)
        return list(grouped.values())

    def _dependency_jobs(self, job: Job, job_map: dict[str, Job]) -> list[Job] | None:
        dependencies: list[Job] = []
        for dependency_id in job.dependency_job_ids:
            dependency = job_map.get(dependency_id)
            if dependency is None:
                return None
            dependencies.append(dependency)
        return dependencies

    def _operation_is_runnable(self, operation_identifier: str) -> bool:
        operation = self.operation_service.require_operation(operation_identifier)
        return operation.status in RUNNABLE_OPERATION_STATUSES


def job_log_level(status: JobStatus) -> JobLogLevel:
    if status in {JobStatus.FAILED, JobStatus.TIMED_OUT, JobStatus.BLOCKED}:
        return JobLogLevel.ERROR
    return JobLogLevel.INFO
