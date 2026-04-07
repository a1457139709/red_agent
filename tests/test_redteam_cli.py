from agent.settings import Settings
from app.dashboard_service import DashboardService
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_service import OperationService
from models.operation import OperationStatus
from main import (
    handle_dashboard_command,
    handle_evidence_command,
    handle_finding_command,
    handle_job_command,
    handle_operation_command,
)


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_operation_commands_create_list_show_pause_and_resume(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    outputs = []
    errors = []
    successes = []
    responses = iter([
        "Surface recon",
        "Inspect public web surface",
        "example.com",
        "example.com",
        "10.0.0.0/24",
        "80,443",
        "http,https",
        "admin.example.com",
        "recon,http",
        "2",
        "60",
        "port_scan",
    ])

    def fake_input(_prompt):
        return next(responses)

    assert handle_operation_command(
        "/operation create",
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    operation = operation_service.list_operations(limit=1)[0]

    assert handle_operation_command(
        "/operation list",
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_operation_command(
        f"/operation show {operation.public_id}",
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_operation_command(
        f"/operation resume {operation.public_id}",
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_operation_command(
        f"/operation pause {operation.public_id}",
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any(f"Created operation {operation.public_id}" in message for message in successes)
    assert any(operation.public_id in message and "Surface recon" in message for message in outputs)
    assert any("Scope Policy" in message and "Allowed Ports:" in message for message in outputs)
    assert any(f"Resumed operation {operation.public_id}" in message for message in successes)
    assert any(f"Paused operation {operation.public_id}" in message for message in successes)
    assert operation_service.require_operation(operation.public_id).status == OperationStatus.PAUSED
    assert not errors


def test_job_commands_create_list_show_cancel_and_review_views(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)
    dashboard_service = DashboardService.from_settings(settings)
    outputs = []
    errors = []
    successes = []

    operation = operation_service.create_operation(title="Probe", objective="Inspect target")
    responses = iter([
        "http_probe",
        "https://example.com",
        '{"method": "GET"}',
        "",
        "30",
        "1",
    ])

    def fake_input(_prompt):
        return next(responses)

    assert handle_job_command(
        f"/job create {operation.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    job = job_service.list_jobs(operation.public_id, limit=1)[0]
    evidence = evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        evidence_type="http_response",
        target_ref=job.target_ref,
        title="HTTP response",
        summary="Captured response",
    )
    finding = finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref=job.target_ref,
        severity="medium",
        confidence="high",
        summary="Service exposed",
    )
    finding_service.link_evidence(finding.public_id, [evidence.public_id])

    assert handle_job_command(
        f"/job list {operation.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_job_command(
        f"/job show {job.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_job_command(
        f"/job cancel {job.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=lambda _prompt: "operator stop",
    )
    assert handle_finding_command(
        f"/finding list {operation.public_id}",
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_finding_command(
        f"/finding show {finding.public_id}",
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_finding_command(
        f"/finding confirm {finding.public_id}",
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_evidence_command(
        f"/evidence show {evidence.public_id}",
        evidence_service=evidence_service,
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_dashboard_command(
        f"/dashboard {operation.public_id}",
        dashboard_service=dashboard_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any(f"Created job {job.public_id}" in message for message in successes)
    assert any(job.public_id in message and "http_probe" in message for message in outputs)
    assert any("Arguments:" in message and "method" in message for message in outputs)
    assert any(f"Requested cancellation for job {job.public_id}" in message for message in successes)
    assert any(finding.public_id in message and "Exposed service" in message for message in outputs)
    assert any("Linked Evidence IDs:" in message and evidence.public_id in message for message in outputs)
    assert any("Linked Finding IDs:" in message and finding.public_id in message for message in outputs)
    assert any("Dashboard Summary" in message and operation.public_id in message for message in outputs)
    assert not errors
