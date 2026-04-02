from types import SimpleNamespace
import subprocess

from domain.operations import OperationService, ScopePolicy
from domain.scope import ScopePolicyService
from storage.redteam import RedTeamStorage
from storage.repositories import OperationRepository, ScopePolicyRepository
from tools.contracts import PortScanRequest
from tools.redteam_executor import RedTeamToolExecutor
from tools.redteam_registry import build_red_team_registry
from tools.security import PortScanTool


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
    return app_data_dir, operation_service, scope_service


def build_policy(operation_id: str) -> ScopePolicy:
    return ScopePolicy.create(
        operation_id=operation_id,
        allowed_hostnames=["app-internal"],
        allowed_ips=["192.168.1.10"],
        allowed_domains=["example.com"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[22, 80, 443, 8080],
        allowed_protocols=["tcp", "https"],
        allowed_tool_categories=["recon"],
    )


def build_tool(tmp_path):
    app_data_dir, operation_service, scope_service = build_services(tmp_path)
    operation = operation_service.create_operation(
        title="Port scan op",
        objective="Run typed port scan",
        workspace=str(tmp_path),
    )
    policy = scope_service.upsert_policy(build_policy(operation.id))
    tool = PortScanTool(scope_service)
    executor = RedTeamToolExecutor(
        build_red_team_registry([tool]),
        app_data_dir=app_data_dir,
    )
    return app_data_dir, operation, policy, tool, executor


def test_port_scan_rejects_missing_ports_and_ranges(tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            validated_scope=policy,
        )
    )

    assert result.status == "failed"
    assert "requires at least one explicit port or port range" in result.summary


def test_port_scan_rejects_invalid_ports_and_ranges(tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    invalid_port = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            ports=[70000],
            validated_scope=policy,
        )
    )
    invalid_range = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            port_ranges=["90-10"],
            validated_scope=policy,
        )
    )

    assert invalid_port.status == "failed"
    assert "Invalid port" in invalid_port.summary
    assert invalid_range.status == "failed"
    assert "Invalid port range" in invalid_range.summary


def test_port_scan_rejects_unsupported_domain_and_cidr_targets(tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    domain_result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="example.com",
            ports=[443],
            validated_scope=policy,
        )
    )
    cidr_result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="10.0.0.0/24",
            ports=[80],
            validated_scope=policy,
        )
    )

    assert domain_result.status == "failed"
    assert "Unsupported target kind" in domain_result.summary
    assert domain_result.structured_result["target_kind"] == "domain"
    assert cidr_result.status == "failed"
    assert cidr_result.structured_result["target_kind"] == "cidr"


def test_port_scan_rejects_out_of_scope_target_before_subprocess(monkeypatch, tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("subprocess.run should not be called for blocked targets")

    monkeypatch.setattr(subprocess, "run", fail_run)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.99",
            ports=[443],
            validated_scope=policy,
        )
    )

    assert result.status == "blocked"
    assert result.structured_result["blocked_reason"] == "ip_not_allowed"


def test_port_scan_rejects_disallowed_port_before_subprocess(monkeypatch, tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("subprocess.run should not be called for blocked ports")

    monkeypatch.setattr(subprocess, "run", fail_run)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            ports=[3306],
            validated_scope=policy,
        )
    )

    assert result.status == "blocked"
    assert result.structured_result["blocked_reason"] == "port_not_allowed"


def test_port_scan_builds_expected_nmap_argv_for_allowed_ip(monkeypatch, tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)
    captured = {}

    def fake_run(argv, capture_output, text, timeout, check):
        captured["argv"] = argv
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        captured["check"] = check
        return SimpleNamespace(
            returncode=0,
            stdout="22/tcp open ssh\n443/tcp closed https\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            ports=[22, 443],
            validated_scope=policy,
            timeout_seconds=15,
        )
    )

    assert captured["argv"] == ["nmap", "-Pn", "-p", "22,443", "192.168.1.10"]
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 15
    assert captured["check"] is False
    assert result.status == "succeeded"
    assert result.structured_result["open_ports"] == [22]


def test_port_scan_hostname_path_is_valid(monkeypatch, tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    def fake_run(argv, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=0,
            stdout="8080/tcp open http-proxy\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="app-internal",
            ports=[8080],
            validated_scope=policy,
        )
    )

    assert result.status == "succeeded"
    assert result.structured_result["target_kind"] == "hostname"
    assert result.structured_result["open_ports"] == [8080]


def test_port_scan_maps_missing_nmap_to_failed_result(monkeypatch, tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    def fake_run(argv, capture_output, text, timeout, check):
        raise FileNotFoundError("nmap not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            ports=[443],
            validated_scope=policy,
        )
    )

    assert result.status == "failed"
    assert "nmap is not installed" in result.summary


def test_port_scan_maps_non_zero_exit_to_failed_result(monkeypatch, tmp_path):
    _app_data_dir, operation, policy, tool, _executor = build_tool(tmp_path)

    def fake_run(argv, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=2,
            stdout="22/tcp open ssh\n",
            stderr="nmap scan failed",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = tool.execute(
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            ports=[22],
            validated_scope=policy,
        )
    )

    assert result.status == "failed"
    assert "exited with code 2" in result.summary
    assert any(item.evidence_type == "port_scan_stderr" for item in result.evidence_items)


def test_red_team_executor_materializes_port_scan_evidence(monkeypatch, tmp_path):
    app_data_dir, operation, policy, _tool, executor = build_tool(tmp_path)

    def fake_run(argv, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=0,
            stdout="22/tcp open ssh\n80/tcp filtered http\n443/tcp closed https\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = executor.execute(
        "port_scan",
        PortScanRequest(
            operation_id=operation.id,
            target="192.168.1.10",
            ports=[22, 80, 443],
            validated_scope=policy,
        ),
    )

    evidence_dir = app_data_dir / "operations" / operation.id / "evidence"

    assert report.result.status == "succeeded"
    assert report.result.structured_result["open_ports"] == [22]
    assert report.result.metrics["filtered_port_count"] == 1
    assert len(report.result.finding_candidates) == 0
    assert evidence_dir.exists()
    assert len(report.materialized_evidence) >= 2
    assert all((app_data_dir / artifact.artifact_path).exists() for artifact in report.materialized_evidence)
