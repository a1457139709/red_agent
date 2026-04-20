from agent.settings import Settings
from app.operation_service import OperationService
from app.session_service import SessionService
from conftest import create_redteam_bundle
from models.operation import Operation, OperationStatus
import pytest
from storage.repositories.operations import OperationRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_operation_service_projects_session_owned_state_for_compatibility_reads(tmp_path):
    settings = build_settings(tmp_path)
    service = OperationService.from_settings(settings)

    bundle = create_redteam_bundle(
        settings,
        title="Web recon",
        objective="Inspect attack surface",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
        denied_targets=["admin.example.com"],
        allowed_tool_categories=["recon"],
        max_concurrency=2,
        rate_limit_per_minute=30,
        confirmation_required_actions=["port_scan"],
    )

    loaded = service.get_operation(bundle.session.public_id)
    with pytest.warns(DeprecationWarning, match="deprecated as a scope-policy access path"):
        policy = service.require_scope_policy(bundle.session.public_id)

    assert loaded is not None
    assert loaded.id == bundle.session.id
    assert loaded.public_id == bundle.session.public_id
    assert loaded.status == OperationStatus.DRAFT
    assert policy.id == bundle.scope_policy.id
    assert policy.operation_id == bundle.session.id
    assert policy.allowed_ports == [80, 443]
    assert policy.max_concurrency == 2
    assert settings.sqlite_path.exists()


def test_operation_service_supports_projected_session_identifier_lookups(tmp_path):
    settings = build_settings(tmp_path)
    service = OperationService.from_settings(settings)

    first = create_redteam_bundle(settings, title="First", objective="One").session
    second = create_redteam_bundle(settings, title="Second", objective="Two").session

    assert service.get_operation(first.id) is not None
    assert service.get_operation(first.public_id) is not None
    assert service.get_operation(first.id[:8]) is not None
    assert service.get_operation(first.id[:8]).id == first.id
    assert service.get_operation(second.public_id).id == second.id


def test_operation_service_prefers_legacy_operation_rows_when_present(tmp_path):
    settings = build_settings(tmp_path)
    repository = OperationRepository(SQLiteStorage(settings.sqlite_path))
    service = OperationService.from_settings(settings)

    legacy = Operation.create(
        title="Legacy",
        objective="Read-only compatibility row",
        workspace=str(tmp_path),
        scope_policy_id="policy-legacy",
        status=OperationStatus.READY,
    )
    repository.create(legacy)

    loaded = service.require_operation(legacy.public_id)

    assert loaded.id == legacy.id
    assert loaded.public_id == legacy.public_id
    assert loaded.status == OperationStatus.READY


def test_operation_service_reflects_session_status_in_projected_reads(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    service = OperationService.from_settings(settings)

    bundle = create_redteam_bundle(
        settings,
        title="Done",
        objective="Finished work",
        status=OperationStatus.READY,
    )
    session_service.update_session_status(bundle.session.public_id, status="completed")

    loaded = service.require_operation(bundle.session.public_id)

    assert loaded.status == OperationStatus.COMPLETED
