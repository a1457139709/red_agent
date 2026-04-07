from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import time

from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from app.security_tool_execution_service import SecurityToolExecutionService
from models.job import JobStatus
from models.operation import OperationStatus
from tools.contracts import EvidenceCandidate, FindingCandidate, SecurityToolResult


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = b"service ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A003
        return


def run_http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_security_tool_execution_service_runs_job_through_scoped_runtime(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    server, thread = run_http_server()
    try:
        port = server.server_address[1]
        operation = operation_service.create_operation(
            title="Recon",
            objective="Probe local service",
            allowed_hosts=["127.0.0.1"],
            allowed_protocols=["http"],
            allowed_ports=[port],
            allowed_tool_categories=["recon"],
            status=OperationStatus.READY,
        )
        job = job_service.create_job(
            operation_identifier=operation.public_id,
            job_type="http_probe",
            target_ref=f"http://127.0.0.1:{port}/health",
        )

        result = execution_service.execute_job(job_identifier=job.public_id)
        refreshed = job_service.require_job(job.public_id)
        logs = job_service.list_logs(job.public_id)
        evidence = EvidenceService.from_settings(settings).list_evidence(operation.public_id, limit=None)

        assert result.status == "succeeded"
        assert isinstance(result.result, SecurityToolResult)
        assert refreshed.status == JobStatus.PENDING
        assert {entry.message for entry in logs} >= {
            "security_tool_execution_succeeded",
            "security_tool_persistence_succeeded",
            "security_tool_validation_started",
        }
        assert len(evidence) == 1
        assert evidence[0].hash_digest is not None
        artifact_path = tmp_path / Path(evidence[0].artifact_path)
        assert artifact_path.exists()
        artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact_payload["source_tool"] == "http_probe"
        assert artifact_payload["evidence_type"] == "http_response"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_security_tool_execution_service_blocks_out_of_scope_targets_before_tool_execution(
    tmp_path,
    monkeypatch,
):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Probe authorized target",
        allowed_domains=["example.com"],
        allowed_protocols=["http"],
        allowed_ports=[80],
        allowed_tool_categories=["recon"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="http://outside.example.org",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("tool execution should not be reached")

    monkeypatch.setattr(execution_service.security_tool_executor, "execute", fail_if_called)

    result = execution_service.execute_job(job_identifier=job.public_id)
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "blocked"
    assert refreshed.status == JobStatus.PENDING


def test_security_tool_execution_service_returns_failed_result_for_validation_errors(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Scan in-scope ports only",
        allowed_hosts=["127.0.0.1"],
        allowed_protocols=["tcp"],
        allowed_ports=[80],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="port_scan",
        target_ref="127.0.0.1",
        arguments={"ports": [81]},
    )

    result = execution_service.execute_job(job_identifier=job.public_id)
    refreshed = job_service.require_job(job.public_id)
    logs = job_service.list_logs(job.public_id)

    assert result.status == "failed"
    assert "outside the scope policy" in result.message
    assert refreshed.status == JobStatus.PENDING
    assert logs[0].message == "security_tool_validation_failed"


def test_security_tool_execution_service_returns_failed_result_for_unknown_tool_types(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Reject unsupported tool types",
        allowed_domains=["example.com"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="unknown_tool",
        target_ref="https://example.com",
    )

    result = execution_service.execute_job(job_identifier=job.public_id)
    refreshed = job_service.require_job(job.public_id)
    logs = job_service.list_logs(job.public_id)

    assert result.status == "failed"
    assert result.message == "Unknown security tool requested: unknown_tool"
    assert refreshed.status == JobStatus.PENDING
    assert logs[0].message == "security_tool_validation_failed"


def test_security_tool_execution_service_reports_timeouts(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Timeout slow probes",
        allowed_hosts=["127.0.0.1"],
        allowed_protocols=["http"],
        allowed_ports=[80],
        allowed_tool_categories=["recon"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="http://127.0.0.1/slow",
        timeout_seconds=1,
    )

    def slow_execute(*args, **kwargs):
        time.sleep(1.2)
        return SecurityToolResult(
            tool_name="http_probe",
            target="http://127.0.0.1/slow",
            summary="slow",
            payload={},
        )

    monkeypatch.setattr(execution_service.security_tool_executor, "execute", slow_execute)

    result = execution_service.execute_job(job_identifier=job.public_id)

    assert result.status == "timed_out"
    assert "timed out" in result.message.lower()


def test_security_tool_execution_service_enforces_job_timeout_over_argument_timeout(
    tmp_path,
    monkeypatch,
):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Honor per-job timeout",
        allowed_domains=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        allowed_tool_categories=["recon"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        arguments={"timeout_seconds": 5},
        timeout_seconds=1,
    )

    captured: dict[str, object] = {}
    original_validate = execution_service.security_tool_executor.validate

    def wrapped_validate(tool_name: str, *, target: str, arguments: dict, policy):
        captured.update(arguments)
        return original_validate(
            tool_name,
            target=target,
            arguments=arguments,
            policy=policy,
        )

    monkeypatch.setattr(execution_service.security_tool_executor, "validate", wrapped_validate)
    monkeypatch.setattr(
        execution_service.security_tool_executor,
        "execute",
        lambda *args, **kwargs: SecurityToolResult(
            tool_name="http_probe",
            target="https://example.com",
            summary="ok",
            payload={},
        ),
    )

    result = execution_service.execute_job(job_identifier=job.public_id)

    assert result.status == "succeeded"
    assert captured["timeout_seconds"] == 1


def test_security_tool_execution_service_persists_findings_and_traceability_for_tls_inspect(
    tmp_path,
    monkeypatch,
):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect TLS findings",
        allowed_domains=["example.com"],
        allowed_protocols=["tls"],
        allowed_ports=[443],
        allowed_tool_categories=["recon"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="tls_inspect",
        target_ref="example.com:443",
    )

    def fake_execute(tool_name: str, *, invocation, target):
        assert tool_name == "tls_inspect"
        return SecurityToolResult(
            tool_name="tls_inspect",
            target=target.normalized_target,
            summary="TLS inspection summary",
            payload={"tls_version": "TLSv1.3"},
            evidence_candidates=[
                EvidenceCandidate(
                    evidence_type="tls_certificate",
                    target_ref=target.normalized_target,
                    title="TLS inspection",
                    summary="Captured certificate details.",
                    content_type="application/json",
                    payload={"tls_version": "TLSv1.3"},
                )
            ],
            finding_candidates=[
                FindingCandidate(
                    finding_type="tls_hostname_mismatch",
                    title="TLS certificate hostname mismatch",
                    target_ref=target.normalized_target,
                    severity="medium",
                    confidence="high",
                    summary="Hostname mismatch observed.",
                    impact="Clients may reject the certificate.",
                    reproduction_notes="Run tls_inspect against the endpoint.",
                    next_action="Confirm SAN coverage.",
                )
            ],
        )

    monkeypatch.setattr(execution_service.security_tool_executor, "execute", fake_execute)

    result = execution_service.execute_job(job_identifier=job.public_id)
    findings = finding_service.list_findings(operation.public_id, limit=None)
    links = finding_service.list_links(operation.public_id)

    assert result.status == "succeeded"
    assert len(findings) == 1
    assert findings[0].finding_type == "tls_hostname_mismatch"
    assert len(links) == 1
    assert links[0].finding_id == findings[0].id


def test_security_tool_execution_service_returns_failed_result_when_evidence_pipeline_fails(
    tmp_path,
    monkeypatch,
):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)

    server, thread = run_http_server()
    try:
        port = server.server_address[1]
        operation = operation_service.create_operation(
            title="Recon",
            objective="Fail artifact persistence",
            allowed_hosts=["127.0.0.1"],
            allowed_protocols=["http"],
            allowed_ports=[port],
            allowed_tool_categories=["recon"],
            status=OperationStatus.READY,
        )
        job = job_service.create_job(
            operation_identifier=operation.public_id,
            job_type="http_probe",
            target_ref=f"http://127.0.0.1:{port}/health",
        )

        monkeypatch.setattr(
            execution_service.evidence_pipeline_service.artifact_manager,
            "write_artifact",
            lambda **kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )

        result = execution_service.execute_job(job_identifier=job.public_id)
        refreshed = job_service.require_job(job.public_id)
        logs = job_service.list_logs(job.public_id)
        evidence = EvidenceService.from_settings(settings).list_evidence(operation.public_id, limit=None)

        assert result.status == "failed"
        assert "Evidence pipeline failed" in result.message
        assert refreshed.status == JobStatus.PENDING
        assert not evidence
        assert any(entry.message == "security_tool_persistence_failed" for entry in logs)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
