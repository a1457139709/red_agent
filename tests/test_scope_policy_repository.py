import sqlite3

from agent.settings import Settings
from models.scope_policy import ScopePolicy
from models.session import Session, SessionMode, SessionPersistenceMode
from storage.repositories.scope_policies import ScopePolicyRepository
from storage.repositories.sessions import SessionRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_scope_policy_repository_round_trips_list_and_integer_fields(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    session_repository = SessionRepository(storage)
    repository = ScopePolicyRepository(storage)
    session = Session.create(
        title="Web recon",
        goal="Inspect attack surface",
        mode=SessionMode.REDTEAM,
        persistence_mode=SessionPersistenceMode.PERSISTENT,
        workspace=str(tmp_path),
    )
    session_repository.create(session)

    policy = ScopePolicy.create(
        session_id=session.id,
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
        denied_targets=["admin.example.com"],
        allowed_tool_categories=["recon", "http"],
        max_concurrency=3,
        rate_limit_per_minute=60,
        confirmation_required_actions=["port_scan"],
    )

    repository.create(policy)
    loaded = repository.get(policy.id)

    assert loaded is not None
    assert loaded.allowed_hosts == ["example.com"]
    assert loaded.allowed_ports == [80, 443]
    assert loaded.allowed_protocols == ["http", "https"]
    assert loaded.allowed_tool_categories == ["recon", "http"]
    assert loaded.max_concurrency == 3
    assert loaded.rate_limit_per_minute == 60
    assert loaded.confirmation_required_actions == ["port_scan"]


def test_scope_policy_repository_rejects_orphan_session_reference(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    SessionRepository(storage)
    repository = ScopePolicyRepository(storage)

    policy = ScopePolicy.create(
        session_id="missing-session",
        allowed_hosts=["example.com"],
    )

    try:
        repository.create(policy)
    except sqlite3.IntegrityError:
        return

    raise AssertionError("Expected sqlite3.IntegrityError for orphan scope policy.")
