from __future__ import annotations

from agent.settings import Settings, get_settings
from agent.state import SessionState
from models.run import (
    Checkpoint,
    Run,
    RunFailureKind,
    RunStatus,
    TaskLogEntry,
    TaskLogLevel,
    duration_ms_between,
    utc_now_iso,
)
from storage.runs import RunRepository
from storage.sqlite import SQLiteStorage


class RunService:
    def __init__(self, repository: RunRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "RunService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        repository = RunRepository(storage)
        return cls(repository, settings)

    def start_run(self, task_id: str) -> Run:
        return self.repository.create_run(Run.create(task_id=task_id))

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
            task_id=run.task_id,
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
            task_id=run.task_id,
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

    def list_runs(self, task_id: str, *, limit: int = 20) -> list[Run]:
        return self.repository.list_runs(task_id, limit=limit)

    def save_checkpoint(
        self,
        *,
        task_id: str,
        session_state: SessionState,
        run_id: str | None = None,
    ) -> Checkpoint:
        checkpoint = Checkpoint.create(
            task_id=task_id,
            run_id=run_id,
            payload=session_state.to_checkpoint_payload(),
        )
        return self.repository.create_checkpoint(checkpoint)

    def load_checkpoint_state(self, checkpoint_id: str) -> SessionState:
        checkpoint = self.repository.get_checkpoint(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        return SessionState.from_checkpoint_payload(checkpoint.payload)

    def write_log(
        self,
        *,
        task_id: str,
        level: TaskLogLevel,
        message: str,
        run_id: str | None = None,
        payload: dict | None = None,
    ) -> TaskLogEntry:
        entry = TaskLogEntry.create(
            task_id=task_id,
            run_id=run_id,
            level=level,
            message=message,
            payload=payload,
        )
        return self.repository.create_log_entry(entry)

    def list_logs(self, task_id: str, *, limit: int = 20) -> list[TaskLogEntry]:
        return self.repository.list_logs(task_id, limit=limit)

    def list_run_logs(self, run_id: str, *, limit: int = 20) -> list[TaskLogEntry]:
        run = self.require_run(run_id)
        return self.repository.list_logs_for_run(run.id, limit=limit)
