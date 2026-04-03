from __future__ import annotations

from agent.settings import Settings, get_settings
from models.memory import MemoryEntry
from storage.repositories.jobs import JobRepository
from storage.repositories.memory import MemoryRepository
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        operation_repository: OperationRepository,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.operation_repository = operation_repository
        self.job_repository = job_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "MemoryService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            MemoryRepository(storage),
            OperationRepository(storage),
            JobRepository(storage),
            settings,
        )

    def create_memory_entry(
        self,
        *,
        operation_identifier: str,
        entry_type: str,
        key: str,
        value,
        summary: str,
        source_job_identifier: str | None = None,
    ) -> MemoryEntry:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        source_job_id: str | None = None
        if source_job_identifier is not None:
            job = self.job_repository.get(source_job_identifier)
            if job is None:
                raise ValueError(f"Job not found: {source_job_identifier}")
            if job.operation_id != operation.id:
                raise ValueError("Memory source job must belong to the same operation.")
            source_job_id = job.id

        entry = MemoryEntry.create(
            operation_id=operation.id,
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

    def list_memory_entries(self, operation_identifier: str, *, limit: int | None = 50) -> list[MemoryEntry]:
        operation = self.operation_repository.get(operation_identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_identifier}")
        return self.repository.list(operation.id, limit=limit)

    def save_memory_entry(self, entry: MemoryEntry) -> MemoryEntry:
        return self.repository.update(entry)
