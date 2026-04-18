from __future__ import annotations

from agent.settings import Settings, get_settings
from models.run import (
    Run,
    RunFailureKind,
    RunStatus,
    SessionLogEntry,
    TaskLogLevel,
    duration_ms_between,
    utc_now_iso,
)
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage
from storage.tasks import TaskRepository
from storage.runs import RunRepository

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class RunService:
    def __init__(
        self,
        repository: RunRepository,
        session_service: SessionService,
        operation_repository: OperationRepository,
        task_repository: TaskRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.task_repository = task_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "RunService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            RunRepository(storage),
            SessionService.from_settings(settings),
            OperationRepository(storage),
            TaskRepository(storage),
            settings,
        )

    def start_run(self, session_identifier: str) -> Run:
        session_id = self._resolve_session_id(session_identifier)
        return self.repository.create_run(Run.create(session_id=session_id))

    def complete_run(
        self,
        run_id: str,
        *,
        step_count: int,
        last_usage: dict | None = None,
        effective_skill_name: str | None = None,
        effective_tools: list[str] | None = None,
        failure_kind: RunFailureKind | None = None,
    ) -> Run:
        run = self.require_run(run_id)
        finished_at = utc_now_iso()
        updated = Run(
            id=run.id,
            public_id=run.public_id,
            session_id=run.session_id,
            status=RunStatus.COMPLETED,
            started_at=run.started_at,
            finished_at=finished_at,
            step_count=step_count,
            last_usage=last_usage or {},
            last_error=None,
            duration_ms=duration_ms_between(run.started_at, finished_at),
            effective_skill_name=effective_skill_name,
            effective_tools=list(effective_tools or []),
            failure_kind=failure_kind.value if isinstance(failure_kind, RunFailureKind) else failure_kind,
        )
        return self.repository.update_run(updated)

    def fail_run(
        self,
        run_id: str,
        *,
        error: str,
        step_count: int = 0,
        last_usage: dict | None = None,
        effective_skill_name: str | None = None,
        effective_tools: list[str] | None = None,
        failure_kind: RunFailureKind | None = None,
    ) -> Run:
        run = self.require_run(run_id)
        finished_at = utc_now_iso()
        updated = Run(
            id=run.id,
            public_id=run.public_id,
            session_id=run.session_id,
            status=RunStatus.FAILED,
            started_at=run.started_at,
            finished_at=finished_at,
            step_count=step_count,
            last_usage=last_usage or {},
            last_error=error,
            duration_ms=duration_ms_between(run.started_at, finished_at),
            effective_skill_name=effective_skill_name,
            effective_tools=list(effective_tools or []),
            failure_kind=failure_kind.value if isinstance(failure_kind, RunFailureKind) else failure_kind,
        )
        return self.repository.update_run(updated)

    def get_run(self, run_id: str) -> Run | None:
        return self.repository.get_run(run_id)

    def require_run(self, run_id: str) -> Run:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        return run

    def list_runs(self, session_identifier: str, *, limit: int | None = 20) -> list[Run]:
        return self.repository.list_runs(self._resolve_session_id(session_identifier), limit=limit)

    def count_runs(self, session_identifier: str) -> int:
        return self.repository.count_runs(self._resolve_session_id(session_identifier))

    def write_log(
        self,
        *,
        session_identifier: str | None = None,
        task_id: str | None = None,
        level: TaskLogLevel,
        message: str,
        run_id: str | None = None,
        payload: dict | None = None,
    ) -> SessionLogEntry:
        identifier = session_identifier or task_id
        if identifier is None:
            raise ValueError("session_identifier is required.")
        entry = SessionLogEntry.create(
            session_id=self._resolve_session_id(identifier),
            run_id=run_id,
            level=level,
            message=message,
            payload=payload,
        )
        return self.repository.create_log_entry(entry)

    def list_logs(self, session_identifier: str, *, limit: int | None = 20) -> list[SessionLogEntry]:
        return self.repository.list_logs(self._resolve_session_id(session_identifier), limit=limit)

    def count_logs(self, session_identifier: str) -> int:
        return self.repository.count_logs(self._resolve_session_id(session_identifier))

    def list_run_logs(self, run_id: str, *, limit: int = 20) -> list[SessionLogEntry]:
        run = self.require_run(run_id)
        return self.repository.list_logs_for_run(run.id, limit=limit)

    def _resolve_session_id(self, identifier: str) -> str:
        return resolve_session_identifier(
            self.session_service,
            identifier,
            operation_repository=self.operation_repository,
            task_repository=self.task_repository,
        )
