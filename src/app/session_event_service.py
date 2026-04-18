from __future__ import annotations

from agent.settings import Settings, get_settings
from models.session_event import SessionEvent, SessionEventLevel, SessionEventType
from storage.repositories.jobs import JobRepository
from storage.repositories.operations import OperationRepository
from storage.repositories.session_events import SessionEventRepository
from storage.sqlite import SQLiteStorage

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class SessionEventService:
    def __init__(
        self,
        repository: SessionEventRepository,
        session_service: SessionService,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SessionEventService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            SessionEventRepository(storage),
            SessionService.from_settings(settings),
            OperationRepository(storage),
            JobRepository(storage),
            settings,
        )

    def create_event(
        self,
        *,
        session_identifier: str | None = None,
        operation_identifier: str | None = None,
        event_type: SessionEventType,
        level: SessionEventLevel,
        tool_name: str,
        tool_category: str,
        target_ref: str,
        job_identifier: str | None = None,
        reason_code: str | None = None,
        message: str = "",
        payload: dict | None = None,
        created_at: str | None = None,
    ) -> SessionEvent:
        session_id = self._resolve_session_id(session_identifier or operation_identifier)
        job_id: str | None = None
        if job_identifier is not None:
            job = self.job_repository.get(job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {job_identifier}")
            if job.session_id != session_id:
                raise ValueError("Session event job must belong to the same session.")
            job_id = job.id

        event = SessionEvent.create(
            session_id=session_id,
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

    def list_events(self, session_identifier: str, *, limit: int | None = 50) -> list[SessionEvent]:
        return self.repository.list(self._resolve_session_id(session_identifier), limit=limit)

    def count_events(self, session_identifier: str) -> int:
        return self.repository.count_since(self._resolve_session_id(session_identifier))

    def count_events_since(
        self,
        session_identifier: str,
        *,
        event_type: SessionEventType | None = None,
        since: str | None = None,
    ) -> int:
        return self.repository.count_since(
            self._resolve_session_id(session_identifier),
            event_type=event_type,
            since=since,
        )

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
        )
