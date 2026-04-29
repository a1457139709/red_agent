from agent.settings import Settings
from conftest import create_redteam_operation
from models.memory import MemoryEntry
from storage.repositories.jobs import JobRepository
from storage.repositories.memory import MemoryRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_memory_repository_lists_entries_and_preserves_structured_value(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    JobRepository(storage)
    repository = MemoryRepository(storage)

    operation = create_redteam_operation(settings, title="Track", objective="Persist facts")
    first = MemoryEntry.create(
        session_id=operation.id,
        entry_type="service",
        key="services",
        value={"ports": [80, 443]},
        summary="Discovered HTTP and HTTPS.",
    )
    second = MemoryEntry.create(
        session_id=operation.id,
        entry_type="note",
        key="observations",
        value=["cdn detected"],
        summary="Target appears behind a CDN.",
    )

    repository.create(first)
    repository.create(second)

    entries = repository.list(operation.id)

    assert {entry.id for entry in entries} == {first.id, second.id}
    values_by_key = {entry.key: entry.value for entry in entries}
    assert values_by_key["observations"] == ["cdn detected"]
    assert values_by_key["services"] == {"ports": [80, 443]}
