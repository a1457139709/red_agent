from agent.settings import Settings
from app.operation_service import OperationService
from models.operation import OperationStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_operation_service_creates_operation_and_scope_policy_atomically(tmp_path):
    settings = build_settings(tmp_path)
    service = OperationService.from_settings(settings)

    operation = service.create_operation(
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

    loaded = service.get_operation(operation.public_id)
    policy = service.require_scope_policy(operation.public_id)

    assert loaded is not None
    assert loaded.id == operation.id
    assert loaded.status == OperationStatus.DRAFT
    assert policy.id == operation.scope_policy_id
    assert policy.operation_id == operation.id
    assert policy.allowed_ports == [80, 443]
    assert policy.max_concurrency == 2
    assert settings.sqlite_path.exists()


def test_operation_service_lists_recent_operations_and_supports_identifier_lookups(tmp_path):
    settings = build_settings(tmp_path)
    service = OperationService.from_settings(settings)

    first = service.create_operation(title="First", objective="One")
    second = service.create_operation(title="Second", objective="Two")

    operations = service.list_operations()

    assert [operation.id for operation in operations] == [second.id, first.id]
    assert service.get_operation(first.id) is not None
    assert service.get_operation(first.public_id) is not None
    assert service.get_operation(first.id[:8]) is not None
    assert service.get_operation(first.id[:8]).id == first.id
