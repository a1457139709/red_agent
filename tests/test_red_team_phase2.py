import pytest

from domain.operations import OperationArtifacts, OperationService, OperationStatus, ScopePolicy
from domain.scope import ScopePolicyService
from storage.redteam import RedTeamStorage
from storage.repositories import OperationRepository, ScopePolicyRepository


def build_services(tmp_path):
    app_data_dir = tmp_path / ".red-code"
    storage = RedTeamStorage(app_data_dir / "agent-redteam.db")
    operation_repository = OperationRepository(storage)
    scope_repository = ScopePolicyRepository(storage)
    scope_service = ScopePolicyService(scope_repository)
    operation_service = OperationService(
        operation_repository,
        scope_service,
        app_data_dir=app_data_dir,
    )
    return operation_service, scope_service


def valid_policy(operation_id: str) -> ScopePolicy:
    return ScopePolicy.create(
        operation_id=operation_id,
        allowed_hostnames=["app.example"],
        allowed_ips=["192.168.1.10"],
        allowed_domains=["example.com"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[53, 80, 443],
        allowed_protocols=["tcp", "https", "dns"],
        allowed_tool_categories=["recon"],
        max_concurrency=2,
    )


def test_scope_policy_service_accepts_valid_policy(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Scope test",
        objective="Validate policy",
        workspace=str(tmp_path),
    )

    policy = scope_service.upsert_policy(valid_policy(operation.id))
    decision = scope_service.validate_policy(policy)

    assert decision.allowed is True
    assert scope_service.get_policy(operation.id) is not None


def test_scope_policy_service_rejects_invalid_cidr_port_and_protocol(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Invalid scope",
        objective="Reject bad values",
        workspace=str(tmp_path),
    )

    with pytest.raises(ValueError, match="Invalid CIDR"):
        scope_service.upsert_policy(
            ScopePolicy.create(
                operation_id=operation.id,
                allowed_ips=["192.168.1.10"],
                allowed_cidrs=["not-a-cidr"],
                allowed_protocols=["tcp"],
                allowed_tool_categories=["recon"],
            )
        )

    with pytest.raises(ValueError, match="Invalid port"):
        scope_service.upsert_policy(
            ScopePolicy.create(
                operation_id=operation.id,
                allowed_ips=["192.168.1.10"],
                allowed_ports=[70000],
                allowed_protocols=["tcp"],
                allowed_tool_categories=["recon"],
            )
        )

    with pytest.raises(ValueError, match="Invalid protocol"):
        scope_service.upsert_policy(
            ScopePolicy.create(
                operation_id=operation.id,
                allowed_ips=["192.168.1.10"],
                allowed_protocols=["ftp"],
                allowed_tool_categories=["recon"],
            )
        )


def test_scope_policy_service_denied_target_overrides_allowlists(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Denied target",
        objective="Deny exact target",
        workspace=str(tmp_path),
    )
    policy = ScopePolicy.create(
        operation_id=operation.id,
        allowed_ips=["192.168.1.10"],
        allowed_protocols=["tcp"],
        allowed_ports=[443],
        denied_targets=["192.168.1.10"],
        allowed_tool_categories=["recon"],
    )
    stored = scope_service.upsert_policy(policy)

    decision = scope_service.check_target(
        stored,
        ip="192.168.1.10",
        port=443,
        protocol="tcp",
    )

    assert decision.allowed is False
    assert decision.reason_code == "target_denied"


def test_scope_policy_service_returns_explicit_scope_decisions(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Decision test",
        objective="Check target decisions",
        workspace=str(tmp_path),
    )
    policy = scope_service.upsert_policy(valid_policy(operation.id))

    allowed = scope_service.check_target(
        policy,
        ip="192.168.1.10",
        port=443,
        protocol="https",
    )
    denied = scope_service.check_target(
        policy,
        domain="forbidden.example",
        protocol="https",
    )

    assert allowed.allowed is True
    assert allowed.reason_code is None
    assert denied.allowed is False
    assert denied.reason_code == "domain_not_allowed"


def test_operation_service_creates_and_loads_operations(tmp_path):
    operation_service, _scope_service = build_services(tmp_path)

    operation = operation_service.create_operation(
        title="Create op",
        objective="Load op",
        workspace=str(tmp_path),
    )
    loaded = operation_service.get_operation(operation.id)

    assert loaded is not None
    assert loaded.id == operation.id
    assert loaded.status == OperationStatus.DRAFT


def test_mark_ready_fails_without_scope_policy(tmp_path):
    operation_service, _scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="No policy",
        objective="Cannot become ready",
        workspace=str(tmp_path),
    )

    with pytest.raises(ValueError, match="without a scope policy"):
        operation_service.mark_ready(operation.id)


def test_mark_ready_succeeds_with_valid_scope_policy(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Ready op",
        objective="Become ready",
        workspace=str(tmp_path),
    )
    scope_service.upsert_policy(valid_policy(operation.id))

    updated = operation_service.mark_ready(operation.id)

    assert updated.status == OperationStatus.READY
    assert operation_service.get_operation(operation.id).status == OperationStatus.READY


def test_operation_service_status_transitions_preserve_fields(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Status op",
        objective="Update status",
        workspace=str(tmp_path),
    )
    scope_service.upsert_policy(valid_policy(operation.id))
    ready = operation_service.mark_ready(operation.id)

    updated = operation_service.set_status(
        ready.id,
        OperationStatus.FAILED,
        last_error_code="scope_blocked",
        last_error_message="Rejected target",
    )

    assert updated.title == "Status op"
    assert updated.objective == "Update status"
    assert updated.status == OperationStatus.FAILED
    assert updated.last_error_code == "scope_blocked"
    assert updated.last_error_message == "Rejected target"


def test_operation_service_delete_removes_artifact_directory(tmp_path):
    operation_service, _scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Delete op",
        objective="Remove artifacts",
        workspace=str(tmp_path),
    )
    artifacts = OperationArtifacts(tmp_path / ".red-code", operation.id).ensure()
    (artifacts.evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")

    operation_service.delete_operation(operation.id)

    assert not artifacts.operation_dir.exists()
    assert operation_service.get_operation(operation.id) is None


def test_scope_and_operation_services_integrate_for_ready_and_admission(tmp_path):
    operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Integration op",
        objective="Ready plus admission",
        workspace=str(tmp_path),
    )
    policy = scope_service.upsert_policy(valid_policy(operation.id))

    ready = operation_service.mark_ready(operation.id)
    denied = scope_service.check_target(
        policy,
        ip="192.168.2.10",
        port=443,
        protocol="https",
    )

    assert ready.status == OperationStatus.READY
    assert denied.allowed is False
    assert denied.reason_code == "ip_not_allowed"
