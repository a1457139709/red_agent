import sqlite3

from agent.settings import Settings
from models.operation import Operation
from models.scope_policy import ScopePolicy
from storage.repositories.operations import OperationRepository
from storage.repositories.scope_policies import ScopePolicyRepository
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
    operation_repository = OperationRepository(storage)
    repository = ScopePolicyRepository(storage)
    operation = Operation.create(
        title="Web recon",
        objective="Inspect attack surface",
        workspace=str(tmp_path),
        scope_policy_id="pending",
    )
    operation_repository.create(operation)

    policy = ScopePolicy.create(
        operation_id=operation.id,
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


def test_scope_policy_repository_rejects_orphan_operation_reference(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    OperationRepository(storage)
    repository = ScopePolicyRepository(storage)

    policy = ScopePolicy.create(
        operation_id="missing-operation",
        allowed_hosts=["example.com"],
    )

    try:
        repository.create(policy)
    except sqlite3.IntegrityError:
        return

    raise AssertionError("Expected sqlite3.IntegrityError for orphan scope policy.")
