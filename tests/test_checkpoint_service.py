import sqlite3

import pytest

from agent.settings import Settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.task_service import TaskService


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_checkpoint_service_saves_blob_loads_and_summarizes_checkpoint(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")

    state = SessionState()
    state.append_user_message("hello")
    state.apply_compressed_summary("summary")
    state.set_usage({"total_tokens": 12})

    checkpoint = checkpoint_service.save_checkpoint(task_id=task.id, session_state=state)
    summary = checkpoint_service.get_checkpoint_summary(checkpoint.id)
    restored = checkpoint_service.load_checkpoint_state(checkpoint.id)

    assert checkpoint.storage_kind == "file_blob"
    assert checkpoint.blob_path is not None
    assert checkpoint.blob_encoding == "json+gzip"
    assert checkpoint.payload_digest is not None
    assert (settings.app_data_dir / checkpoint.blob_path).exists()
    assert summary is not None
    assert summary.storage_kind == "file_blob"
    assert summary.payload_size_bytes > 0
    assert summary.history_message_count == 0
    assert summary.has_compressed_summary is True
    assert restored.context_summary == "summary"
    assert restored.last_usage == {"total_tokens": 12}


def test_checkpoint_service_lists_recent_checkpoint_summaries(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")

    first = SessionState()
    first.append_user_message("first")
    second = SessionState()
    second.append_user_message("second")

    first_record = checkpoint_service.save_checkpoint(task_id=task.id, session_state=first)
    second_record = checkpoint_service.save_checkpoint(task_id=task.id, session_state=second)
    summaries = checkpoint_service.list_checkpoints(task.id)

    assert [summary.id for summary in summaries] == [second_record.id, first_record.id]
    assert all(summary.storage_kind == "file_blob" for summary in summaries)


def test_checkpoint_service_rejects_digest_mismatch(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")

    state = SessionState()
    state.append_user_message("hello")
    checkpoint = checkpoint_service.save_checkpoint(task_id=task.id, session_state=state)
    blob_path = settings.app_data_dir / checkpoint.blob_path
    blob_path.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="digest mismatch"):
        checkpoint_service.load_checkpoint_state(checkpoint.id)


def test_checkpoint_service_rejects_legacy_inline_schema(tmp_path):
    settings = build_settings(tmp_path)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.sqlite_path) as connection:
        connection.execute(
            """
            CREATE TABLE checkpoints (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                run_id TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()

    with pytest.raises(ValueError, match="older checkpoint schema"):
        CheckpointService.from_settings(settings)
