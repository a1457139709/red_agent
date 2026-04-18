import gzip
import hashlib
import json
import sqlite3

import pytest

from agent.settings import Settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.session_service import SessionService
from app.task_service import TaskService


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def create_session_checkpoint_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            run_id TEXT,
            created_at TEXT NOT NULL,
            storage_kind TEXT NOT NULL,
            blob_path TEXT NOT NULL,
            blob_encoding TEXT NOT NULL,
            payload_size_bytes INTEGER NOT NULL,
            payload_digest TEXT NOT NULL,
            history_message_count INTEGER NOT NULL,
            history_text_bytes INTEGER NOT NULL,
            has_compressed_summary INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def test_checkpoint_service_saves_blob_loads_and_summarizes_checkpoint(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")
    session = session_service.require_session(task.session_id)

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
    assert checkpoint.blob_path.startswith(f"sessions/{session.id}/memory/checkpoints/")
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



def test_checkpoint_service_deletes_checkpoint_metadata_and_blob(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")
    session = session_service.require_session(task.session_id)

    state = SessionState()
    state.append_user_message("hello")
    checkpoint = checkpoint_service.save_checkpoint(task_id=task.id, session_state=state)
    blob_path = settings.app_data_dir / checkpoint.blob_path

    checkpoint_service.delete_checkpoint(checkpoint.id)

    assert checkpoint_service.get_checkpoint_record(checkpoint.id) is None
    assert checkpoint_service.get_checkpoint_summary(checkpoint.id) is None
    assert not blob_path.exists()
    assert not (settings.sessions_dir / session.id / "memory" / "checkpoints").exists()



def test_checkpoint_service_prunes_older_checkpoints(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")

    created = []
    for index in range(3):
        state = SessionState()
        state.append_user_message(f"hello-{index}")
        created.append(checkpoint_service.save_checkpoint(task_id=task.id, session_state=state))

    deleted_count = checkpoint_service.prune_checkpoints(task.id, keep_last=1)
    remaining = checkpoint_service.list_checkpoints(task.id)

    assert deleted_count == 2
    assert len(remaining) == 1
    assert remaining[0].id == created[-1].id
    assert checkpoint_service.get_checkpoint_record(created[0].id) is None
    assert checkpoint_service.get_checkpoint_record(created[1].id) is None
    assert checkpoint_service.get_checkpoint_record(created[2].id) is not None



def test_checkpoint_service_prune_validates_keep_last(tmp_path):
    settings = build_settings(tmp_path)
    checkpoint_service = CheckpointService.from_settings(settings)

    with pytest.raises(ValueError, match="keep_last"):
        checkpoint_service.prune_checkpoints("task-id", keep_last=-1)


def test_checkpoint_service_migrates_legacy_blob_paths_into_session_directory(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")
    session = session_service.require_session(task.session_id)
    legacy_relative_path = "memory/checkpoints/2026/04/chk_legacy.json.gz"
    legacy_blob_path = settings.app_data_dir / legacy_relative_path
    legacy_blob_path.parent.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(b'{"version": 2, "session_state": {"history": []}}')
    payload_digest = hashlib.sha256(payload).hexdigest()
    legacy_blob_path.write_bytes(payload)

    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.sqlite_path) as connection:
        create_session_checkpoint_table(connection)
        connection.execute(
            """
            INSERT INTO session_checkpoints (
                id, session_id, run_id, created_at, storage_kind, blob_path, blob_encoding,
                payload_size_bytes, payload_digest, history_message_count, history_text_bytes,
                has_compressed_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-checkpoint",
                session.id,
                None,
                "2026-04-17T12:00:00+00:00",
                "file_blob",
                legacy_relative_path,
                "json+gzip",
                len(payload),
                payload_digest,
                0,
                0,
                0,
            ),
        )
        connection.commit()

    checkpoint_service = CheckpointService.from_settings(settings)
    migrated = checkpoint_service.require_checkpoint_record("legacy-checkpoint")
    migrated_blob_path = settings.app_data_dir / migrated.blob_path

    assert migrated.blob_path == f"sessions/{session.id}/memory/checkpoints/2026/04/chk_legacy.json.gz"
    assert migrated_blob_path.exists()
    assert not legacy_blob_path.exists()

    checkpoint_service = CheckpointService.from_settings(settings)
    migrated_again = checkpoint_service.require_checkpoint_record("legacy-checkpoint")
    assert migrated_again.blob_path == migrated.blob_path


def test_checkpoint_service_migration_fails_on_conflicting_blob_files(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")
    session = session_service.require_session(task.session_id)
    legacy_relative_path = "memory/checkpoints/2026/04/chk_conflict.json.gz"
    target_relative_path = f"sessions/{session.id}/{legacy_relative_path}"
    legacy_blob_path = settings.app_data_dir / legacy_relative_path
    target_blob_path = settings.app_data_dir / target_relative_path
    legacy_blob_path.parent.mkdir(parents=True, exist_ok=True)
    target_blob_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_blob_path.write_bytes(gzip.compress(b'{"version": 2, "session_state": {"history": []}}'))
    target_blob_path.write_bytes(gzip.compress(b'{"version": 2, "session_state": {"history": ["different"]}}'))
    payload_digest = hashlib.sha256(legacy_blob_path.read_bytes()).hexdigest()

    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.sqlite_path) as connection:
        create_session_checkpoint_table(connection)
        connection.execute(
            """
            INSERT INTO session_checkpoints (
                id, session_id, run_id, created_at, storage_kind, blob_path, blob_encoding,
                payload_size_bytes, payload_digest, history_message_count, history_text_bytes,
                has_compressed_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "conflict-checkpoint",
                session.id,
                None,
                "2026-04-17T12:00:00+00:00",
                "file_blob",
                legacy_relative_path,
                "json+gzip",
                legacy_blob_path.stat().st_size,
                payload_digest,
                0,
                0,
                0,
            ),
        )
        connection.commit()

    with pytest.raises(ValueError, match="migration conflict"):
        CheckpointService.from_settings(settings)


def test_checkpoint_service_migrates_public_id_scoped_blob_paths_into_raw_session_id_directory(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")
    session = session_service.require_session(task.session_id)
    legacy_relative_path = f"sessions/{session.public_id}/memory/checkpoints/2026/04/chk_public.json.gz"
    legacy_blob_path = settings.app_data_dir / legacy_relative_path
    legacy_blob_path.parent.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(b'{"version": 2, "session_state": {"history": []}}')
    payload_digest = hashlib.sha256(payload).hexdigest()
    legacy_blob_path.write_bytes(payload)

    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.sqlite_path) as connection:
        create_session_checkpoint_table(connection)
        connection.execute(
            """
            INSERT INTO session_checkpoints (
                id, session_id, run_id, created_at, storage_kind, blob_path, blob_encoding,
                payload_size_bytes, payload_digest, history_message_count, history_text_bytes,
                has_compressed_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "public-id-checkpoint",
                session.id,
                None,
                "2026-04-17T12:00:00+00:00",
                "file_blob",
                legacy_relative_path,
                "json+gzip",
                len(payload),
                payload_digest,
                0,
                0,
                0,
            ),
        )
        connection.commit()

    checkpoint_service = CheckpointService.from_settings(settings)
    migrated = checkpoint_service.require_checkpoint_record("public-id-checkpoint")

    assert migrated.blob_path == f"sessions/{session.id}/memory/checkpoints/2026/04/chk_public.json.gz"
    assert (settings.app_data_dir / migrated.blob_path).exists()
    assert not legacy_blob_path.exists()


def test_checkpoint_service_round_trips_unicode_through_gzip_blob(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")

    state = SessionState()
    state.append_user_message("你好，世界")
    state.compressed_summary = "摘要：保留中文"
    state.set_usage({"total_tokens": 34})

    checkpoint = checkpoint_service.save_checkpoint(task_id=task.id, session_state=state)
    blob_path = settings.app_data_dir / checkpoint.blob_path

    raw_payload = gzip.decompress(blob_path.read_bytes()).decode("utf-8")
    decoded_payload = json.loads(raw_payload)
    restored = checkpoint_service.load_checkpoint_state(checkpoint.id)

    assert decoded_payload["session_state"]["history"][0]["content"] == "你好，世界"
    assert decoded_payload["session_state"]["compressed_summary"] == "摘要：保留中文"
    assert restored.history[0].content == "你好，世界"
    assert restored.context_summary == "摘要：保留中文"
    assert restored.last_usage == {"total_tokens": 34}
