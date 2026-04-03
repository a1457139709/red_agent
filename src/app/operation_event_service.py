from __future__ import annotations

from agent.settings import Settings, get_settings
from models.operation_event import OperationEvent, OperationEventLevel, OperationEventType
from storage.repositories.jobs import JobRepository
from storage.repositories.operation_events import OperationEventRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage


class OperationEventService:
    def __init__(
        self,
        repository: OperationEventRepository,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OperationEventService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            OperationEventRepository(storage),
            OperationRepository(storage),
            JobRepository(storage),
            settings,
        )

    def create_event(
        self,
        *,
        operation_identifier: str,
        event_type: OperationEventType,
        level: OperationEventLevel,
        tool_name: str,
        tool_category: str,
        target_ref: str,
        job_identifier: str | None = None,
        reason_code: str | None = None,
        message: str = "",
        payload: dict | None = None,
        created_at: str | None = None,
    ) -> OperationEvent:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")

        job_id: str | None = None
        if job_identifier is not None:
            job = self.job_repository.get(job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {job_identifier}")
            if job.operation_id != operation.id:
                raise ValueError("Operation event job must belong to the same operation.")
            job_id = job.id

        event = OperationEvent.create(
            operation_id=operation.id,
            job_id=job_id,
            event_type=event_type,
            level=level,
            tool_name=tool_name,
            tool_category=tool_category,
            target_ref=target_ref,
            reason_code=reason_code,
            message=message,
            payload=payload,
            created_at=created_at,
        )
        return self.repository.create(event)

    def list_events(self, operation_identifier: str, *, limit: int | None = 50) -> list[OperationEvent]:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        return self.repository.list(operation.id, limit=limit)

    def count_events_since(
        self,
        operation_identifier: str,
        *,
        event_type: OperationEventType | None = None,
        since: str | None = None,
    ) -> int:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        return self.repository.count_since(operation.id, event_type=event_type, since=since)
