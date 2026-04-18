from __future__ import annotations

from agent.settings import Settings, get_settings
from models.job import Job, JobLogEntry, JobLogLevel, JobStatus
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage

from .session_scope import resolve_session_identifier
from .session_service import SessionService


def _ensure_non_negative_int(value: int, *, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0.")


def _ensure_positive_int(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        session_service: SessionService,
        operation_repository: OperationRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "JobService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            JobRepository(storage),
            SessionService.from_settings(settings),
            OperationRepository(storage),
            settings,
        )

    def create_job(
        self,
        *,
        session_identifier: str | None = None,
        operation_identifier: str | None = None,
        job_type: str,
        target_ref: str,
        arguments: dict | None = None,
        dependency_job_ids: list[str] | None = None,
        timeout_seconds: int | None = None,
        retry_limit: int = 0,
        status: JobStatus = JobStatus.PENDING,
    ) -> Job:
        session_id = self._resolve_session_id(session_identifier or operation_identifier)
        if timeout_seconds is not None:
            _ensure_positive_int(timeout_seconds, field_name="timeout_seconds")
        _ensure_non_negative_int(retry_limit, field_name="retry_limit")

        resolved_dependency_ids: list[str] = []
        for dependency_identifier in dependency_job_ids or []:
            dependency = self.repository.get(dependency_identifier)
            if dependency is None:
                raise ValueError(f"Dependency job not found: {dependency_identifier}")
            if dependency.session_id != session_id:
                raise ValueError("Dependency job must belong to the same session.")
            resolved_dependency_ids.append(dependency.id)

        job = Job.create(
            session_id=session_id,
            job_type=job_type,
            target_ref=target_ref,
            status=status,
            arguments=arguments,
            dependency_job_ids=resolved_dependency_ids,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        return self.repository.create(job)

    def get_job(self, identifier: str) -> Job | None:
        return self.repository.get(identifier)

    def require_job(self, identifier: str) -> Job:
        job = self.get_job(identifier)
        if job is None:
            raise ValueError(f"Job not found: {identifier}")
        return job

    def list_jobs(
        self,
        session_identifier: str,
        *,
        status: JobStatus | None = None,
        limit: int | None = 50,
    ) -> list[Job]:
        return self.repository.list(self._resolve_session_id(session_identifier), status=status, limit=limit)

    def count_jobs(
        self,
        session_identifier: str,
        *,
        status: JobStatus | None = None,
    ) -> int:
        return self.repository.count(self._resolve_session_id(session_identifier), status=status)

    def save_job(self, job: Job) -> Job:
        if job.timeout_seconds is not None:
            _ensure_positive_int(job.timeout_seconds, field_name="timeout_seconds")
        _ensure_non_negative_int(job.retry_limit, field_name="retry_limit")
        _ensure_non_negative_int(job.retry_count, field_name="retry_count")
        return self.repository.update(job)

    def write_log(
        self,
        *,
        job_identifier: str,
        level: JobLogLevel,
        message: str,
        payload: dict | None = None,
    ) -> JobLogEntry:
        job = self.require_job(job_identifier)
        entry = JobLogEntry.create(
            job_id=job.id,
            level=level,
            message=message,
            payload=payload,
        )
        return self.repository.create_log_entry(entry)

    def list_logs(self, job_identifier: str, *, limit: int = 20) -> list[JobLogEntry]:
        job = self.require_job(job_identifier)
        return self.repository.list_logs(job.id, limit=limit)

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
        )
