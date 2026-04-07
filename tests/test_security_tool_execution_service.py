from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from app.security_tool_execution_service import SecurityToolExecutionService
from models.job import JobStatus
from models.operation import OperationStatus
from tools.contracts import SecurityToolResult


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

        assert result.status == "succeeded"
        assert isinstance(result.result, SecurityToolResult)
        assert refreshed.status == JobStatus.SUCCEEDED
        assert logs[0].message == "security_tool_execution_succeeded"
        assert logs[1].message == "security_tool_validation_started"
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
    assert refreshed.status == JobStatus.BLOCKED


def test_security_tool_execution_service_marks_validation_failures_as_failed(tmp_path):
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

    with pytest.raises(ValueError, match="outside the scope policy"):
        execution_service.execute_job(job_identifier=job.public_id)

    refreshed = job_service.require_job(job.public_id)
    logs = job_service.list_logs(job.public_id)

    assert refreshed.status == JobStatus.FAILED
    assert logs[0].message == "security_tool_validation_failed"


def test_security_tool_execution_service_marks_unknown_job_type_as_failed(tmp_path):
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

    with pytest.raises(ValueError, match="Unknown security tool requested: unknown_tool"):
        execution_service.execute_job(job_identifier=job.public_id)

    refreshed = job_service.require_job(job.public_id)
    logs = job_service.list_logs(job.public_id)

    assert refreshed.status == JobStatus.FAILED
    assert refreshed.last_error == "Unknown security tool requested: unknown_tool"
    assert logs[0].message == "security_tool_validation_failed"
