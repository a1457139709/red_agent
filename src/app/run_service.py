from __future__ import annotations

from agent.settings import Settings, get_settings
from agent.state import SessionState
from models.run import Checkpoint, Run, RunStatus, TaskLogEntry, TaskLogLevel, utc_now_iso
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
    ) -> Run:
        run = self._require_run(run_id)
        updated = Run(
            id=run.id,
            task_id=run.task_id,
            status=RunStatus.COMPLETED,
            started_at=run.started_at,
            finished_at=utc_now_iso(),
            step_count=step_count,
            last_usage=last_usage or {},
            last_error=None,
        )
        return self.repository.update_run(updated)

    def fail_run(
        self,
        run_id: str,
        *,
        error: str,
        step_count: int = 0,
        last_usage: dict | None = None,
    ) -> Run:
        run = self._require_run(run_id)
        updated = Run(
            id=run.id,
            task_id=run.task_id,
            status=RunStatus.FAILED,
            started_at=run.started_at,
            finished_at=utc_now_iso(),
            step_count=step_count,
            last_usage=last_usage or {},
            last_error=error,
        )
        return self.repository.update_run(updated)

    def get_run(self, run_id: str) -> Run | None:
        return self.repository.get_run(run_id)

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

    def _require_run(self, run_id: str) -> Run:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        return run
