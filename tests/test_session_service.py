import inspect

from agent.settings import Settings
from app.session_service import SessionService
from models.session import (
    Session,
    SessionMode,
    SessionPersistenceMode,
    SessionStatus,
    SessionTarget,
    SessionTargetKind,
)


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_session_service_defaults_persistence_mode_by_session_mode(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)

    normal = service.create_session(
        title="Normal",
        goal="Ad hoc help",
        mode=SessionMode.NORMAL,
    )
    redteam = service.create_session(
        title="Redteam",
        goal="Persistent target review",
        mode=SessionMode.REDTEAM,
    )

    assert normal.persistence_mode == SessionPersistenceMode.EPHEMERAL
    assert redteam.persistence_mode == SessionPersistenceMode.PERSISTENT


def test_session_service_handles_legal_and_illegal_status_transitions(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    session = service.create_session(
        title="Lifecycle",
        goal="Exercise status rules",
        mode=SessionMode.REDTEAM,
    )

    active = service.update_session_status(session.public_id, SessionStatus.ACTIVE)
    completed = service.update_session_status(active.public_id, SessionStatus.COMPLETED)

    assert active.status == SessionStatus.ACTIVE
    assert completed.status == SessionStatus.COMPLETED
    assert completed.closed_at is not None

    try:
        service.update_session_status(completed.public_id, SessionStatus.ACTIVE)
    except ValueError as exc:
        assert "completed -> active" in str(exc)
    else:
        raise AssertionError("Expected invalid terminal-state transition to fail")


def test_session_service_gets_latest_and_updates_targets(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    first = service.create_session(
        title="First",
        goal="One",
        mode=SessionMode.NORMAL,
    )
    second = service.create_session(
        title="Second",
        goal="Two",
        mode=SessionMode.REDTEAM,
    )

    updated = service.update_session_targets(
        first.public_id,
        targets=[
            SessionTarget(kind=SessionTargetKind.DOMAIN, value="example.com"),
            SessionTarget(kind=SessionTargetKind.IP, value="93.184.216.34"),
        ],
    )

    latest = service.get_latest_session()
    loaded = service.require_session(updated.public_id)

    assert latest is not None
    assert latest.id == updated.id
    assert loaded.target_summary == "example.com, 93.184.216.34"
    assert [target.kind for target in loaded.targets] == [
        SessionTargetKind.DOMAIN,
        SessionTargetKind.IP,
    ]
    assert second.id != latest.id


def test_session_service_updates_authorization_and_preserves_last_error_by_default(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    session = service.create_session(
        title="Auth",
        goal="Track engagement context",
        mode=SessionMode.REDTEAM,
    )

    service.update_session_status(
        session.public_id,
        SessionStatus.ACTIVE,
        last_error="temporary failure",
    )
    paused = service.update_session_status(session.public_id, SessionStatus.PAUSED)
    noted = service.update_authorization_note(
        paused.public_id,
        "Authorized only for the listed scope.",
    )

    assert paused.last_error == "temporary failure"
    assert noted.authorization_note == "Authorized only for the listed scope."


def test_session_service_module_has_no_legacy_top_level_service_dependency(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    created = service.create_session(
        title="Independent",
        goal="No legacy service dependency",
        mode=SessionMode.NORMAL,
    )

    source = inspect.getsource(SessionService)

    assert created.public_id == "S0001"
    assert "TaskService" not in source
    assert "OperationService" not in source
    assert "task_service" not in source
    assert "operation_service" not in source


def test_session_service_save_session_persists_manual_changes(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    session = service.create_session(
        title="Saved",
        goal="Persist edits",
        mode=SessionMode.REDTEAM,
        targets=[SessionTarget(kind=SessionTargetKind.HOST, value="staging.example.com")],
    )

    session.metadata["owner"] = "analyst"
    session.target_summary = None
    saved = service.save_session(session)
    loaded = service.require_session(saved.public_id)

    assert loaded.metadata == {"owner": "analyst"}
    assert loaded.target_summary == "staging.example.com"


def test_session_service_save_session_rejects_reviving_terminal_status(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    session = service.create_session(
        title="Terminal",
        goal="Enforce lifecycle rules on save",
        mode=SessionMode.REDTEAM,
    )

    service.update_session_status(session.public_id, SessionStatus.ACTIVE)
    completed = service.update_session_status(session.public_id, SessionStatus.COMPLETED)

    completed.status = SessionStatus.ACTIVE
    completed.closed_at = None

    try:
        service.save_session(completed)
    except ValueError as exc:
        assert "completed -> active" in str(exc)
    else:
        raise AssertionError("Expected invalid terminal-state save to fail")

    persisted = service.require_session(session.public_id)

    assert persisted.status == SessionStatus.COMPLETED
    assert persisted.closed_at is not None


def test_session_service_save_session_sets_closed_at_for_terminal_status(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    session = service.create_session(
        title="Close on save",
        goal="Auto-populate closed_at",
        mode=SessionMode.REDTEAM,
    )

    service.update_session_status(session.public_id, SessionStatus.ACTIVE)
    active = service.require_session(session.public_id)
    active.status = SessionStatus.CANCELLED
    active.closed_at = None

    saved = service.save_session(active)

    assert saved.status == SessionStatus.CANCELLED
    assert saved.closed_at is not None


def test_session_service_create_session_sets_closed_at_for_terminal_status(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)

    created = service.create_session(
        title="Done already",
        goal="Support terminal bootstrap states",
        mode=SessionMode.NORMAL,
        status=SessionStatus.COMPLETED,
    )

    assert created.closed_at == created.updated_at


def test_session_service_can_use_model_instances_created_outside_service(tmp_path):
    settings = build_settings(tmp_path)
    service = SessionService.from_settings(settings)
    external = Session.create(
        title="External",
        goal="Use external model helpers",
        mode=SessionMode.NORMAL,
        persistence_mode=SessionPersistenceMode.EPHEMERAL,
        workspace=str(tmp_path),
    )

    saved = service.repository.create(external)

    assert service.get_session(saved.public_id) is not None
