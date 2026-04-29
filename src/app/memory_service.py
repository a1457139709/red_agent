from __future__ import annotations

from agent.settings import Settings, get_settings
from models.memory import MemoryEntry
from storage.repositories.jobs import JobRepository
from storage.repositories.memory import MemoryRepository
from storage.sqlite import SQLiteStorage

from .session_scope import resolve_session_identifier
from .session_service import SessionService


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        session_service: SessionService,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "MemoryService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            MemoryRepository(storage),
            SessionService.from_settings(settings),
            JobRepository(storage),
            settings,
        )

    def create_memory_entry(
        self,
        *,
        session_identifier: str,
        entry_type: str,
        key: str,
        value,
        summary: str,
        source_job_identifier: str | None = None,
    ) -> MemoryEntry:
        session_id = self._resolve_session_id(session_identifier)
        source_job_id: str | None = None
        if source_job_identifier is not None:
            job = self.job_repository.get(source_job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {source_job_identifier}")
            if job.session_id != session_id:
                raise ValueError("Memory source job must belong to the same session.")
            source_job_id = job.id

        entry = MemoryEntry.create(
            session_id=session_id,
            source_job_id=source_job_id,
            entry_type=entry_type,
            key=key,
            value=value,
            summary=summary,
        )
        return self.repository.create(entry)

    def get_memory_entry(self, identifier: str) -> MemoryEntry | None:
        return self.repository.get(identifier)

    def require_memory_entry(self, identifier: str) -> MemoryEntry:
        entry = self.get_memory_entry(identifier)
        if entry is None:
            raise ValueError(f"Memory entry not found: {identifier}")
        return entry

    def list_memory_entries(self, session_identifier: str, *, limit: int | None = 50) -> list[MemoryEntry]:
        return self.repository.list(self._resolve_session_id(session_identifier), limit=limit)

    def count_memory_entries(self, session_identifier: str) -> int:
        return self.repository.count(self._resolve_session_id(session_identifier))

    def save_memory_entry(self, entry: MemoryEntry) -> MemoryEntry:
        return self.repository.update(entry)

    def _resolve_session_id(self, identifier: str | None) -> str:
        if not identifier:
            raise ValueError("session_identifier is required.")
        return resolve_session_identifier(self.session_service, identifier)
