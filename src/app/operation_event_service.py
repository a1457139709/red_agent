from __future__ import annotations

"""Legacy OperationEventService compatibility wrapper over SessionEventService."""

import warnings

from agent.settings import Settings, get_settings
from models.operation_event import OperationEvent, OperationEventLevel, OperationEventType
from models.session_event import SessionEventLevel, SessionEventType
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage

from .session_event_service import SessionEventService


class OperationEventService:
    def __init__(
        self,
        session_event_service: SessionEventService,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.session_event_service = session_event_service
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OperationEventService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            SessionEventService.from_settings(settings),
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
        warnings.warn(
            "OperationEventService.create_event() is deprecated as a primary write path. "
            "Use SessionEventService.create_event() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        event = self.session_event_service.create_event(
            operation_identifier=operation_identifier,
            event_type=SessionEventType(event_type.value),
            level=SessionEventLevel(level.value),
            tool_name=tool_name,
            tool_category=tool_category,
            target_ref=target_ref,
            job_identifier=job_identifier,
            reason_code=reason_code,
            message=message,
            payload=payload,
            created_at=created_at,
        )
        return OperationEvent(
            id=event.id,
            operation_id=event.session_id,
            job_id=event.job_id,
            event_type=OperationEventType(event.event_type.value),
            level=OperationEventLevel(event.level.value),
            tool_name=event.tool_name,
            tool_category=event.tool_category,
            target_ref=event.target_ref,
            reason_code=event.reason_code,
            message=event.message,
            payload=event.payload,
            created_at=event.created_at,
        )

    def list_events(self, operation_identifier: str, *, limit: int | None = 50) -> list[OperationEvent]:
        return [
            OperationEvent(
                id=event.id,
                operation_id=event.session_id,
                job_id=event.job_id,
                event_type=OperationEventType(event.event_type.value),
                level=OperationEventLevel(event.level.value),
                tool_name=event.tool_name,
                tool_category=event.tool_category,
                target_ref=event.target_ref,
                reason_code=event.reason_code,
                message=event.message,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in self.session_event_service.list_events(operation_identifier, limit=limit)
        ]

    def count_events_since(
        self,
        operation_identifier: str,
        *,
        event_type: OperationEventType | None = None,
        since: str | None = None,
    ) -> int:
        return self.session_event_service.count_events_since(
            operation_identifier,
            event_type=SessionEventType(event_type.value) if event_type is not None else None,
            since=since,
        )
