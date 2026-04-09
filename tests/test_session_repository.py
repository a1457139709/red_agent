from agent.settings import Settings
from models.session import (
    Session,
    SessionMode,
    SessionPersistenceMode,
    SessionStatus,
    SessionTarget,
    SessionTargetKind,
)
from storage.repositories.sessions import SessionRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_repository(tmp_path) -> SessionRepository:
    settings = build_settings(tmp_path)
    return SessionRepository(SQLiteStorage(settings.sqlite_path))


def test_session_repository_creates_and_reads_by_multiple_identifiers(tmp_path):
    repository = build_repository(tmp_path)
    session = Session.create(
        title="Example Recon",
        goal="Inspect the target",
        mode=SessionMode.REDTEAM,
        persistence_mode=SessionPersistenceMode.PERSISTENT,
        workspace=str(tmp_path),
        targets=[SessionTarget(kind=SessionTargetKind.DOMAIN, value="example.com")],
        metadata={"source": "test"},
    )

    repository.create(session)

    by_id = repository.get(session.id)
    by_public_id = repository.get(session.public_id)
    by_prefix = repository.get(session.id[:8])

    assert session.public_id == "S0001"
    assert by_id is not None
    assert by_public_id is not None
    assert by_prefix is not None
    assert by_id.id == session.id
    assert by_public_id.id == session.id
    assert by_prefix.id == session.id
    assert by_id.targets[0].value == "example.com"
    assert by_id.metadata == {"source": "test"}


def test_session_repository_lists_by_recent_update_and_filters(tmp_path):
    repository = build_repository(tmp_path)
    first = Session.create(
        title="First Session",
        goal="One",
        mode=SessionMode.NORMAL,
        persistence_mode=SessionPersistenceMode.EPHEMERAL,
        workspace=str(tmp_path),
    )
    second = Session.create(
        title="Second Session",
        goal="Two",
        mode=SessionMode.REDTEAM,
        persistence_mode=SessionPersistenceMode.PERSISTENT,
        workspace=str(tmp_path),
        status=SessionStatus.ACTIVE,
    )

    repository.create(first)
    repository.create(second)

    first.status = SessionStatus.ACTIVE
    first.updated_at = "9999-01-01T00:00:00+00:00"
    repository.update(first)

    sessions = repository.list()
    redteam = repository.list(mode=SessionMode.REDTEAM)
    active = repository.list(status=SessionStatus.ACTIVE)
    title_matches = repository.list(title_query="second")

    assert [session.id for session in sessions] == [first.id, second.id]
    assert [session.id for session in redteam] == [second.id]
    assert [session.id for session in active] == [first.id, second.id]
    assert [session.id for session in title_matches] == [second.id]


def test_session_repository_round_trips_targets_and_metadata_json(tmp_path):
    repository = build_repository(tmp_path)
    session = Session.create(
        title="Stored Targets",
        goal="Keep structured JSON",
        mode=SessionMode.REDTEAM,
        persistence_mode=SessionPersistenceMode.PERSISTENT,
        workspace=str(tmp_path),
        targets=[
            SessionTarget(kind=SessionTargetKind.DOMAIN, value="example.com"),
            SessionTarget(kind=SessionTargetKind.CIDR, value="10.0.0.0/24", note="corp subnet"),
        ],
        metadata={"nested": {"enabled": True}},
    )

    repository.create(session)
    loaded = repository.require(session.public_id)

    assert [target.kind for target in loaded.targets] == [
        SessionTargetKind.DOMAIN,
        SessionTargetKind.CIDR,
    ]
    assert loaded.targets[1].note == "corp subnet"
    assert loaded.metadata == {"nested": {"enabled": True}}
