from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from main import handle_job_command, handle_operation_command


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_operation_commands_create_list_and_show(tmp_path):
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

    assert any(f"Created operation {operation.public_id}" in message for message in successes)
    assert any(operation.public_id in message and "Surface recon" in message for message in outputs)
    assert any("Scope Policy" in message and "Allowed Ports:" in message for message in outputs)
    assert not errors


def test_job_commands_create_list_and_show(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
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

    assert any(f"Created job {job.public_id}" in message for message in successes)
    assert any(job.public_id in message and "http_probe" in message for message in outputs)
    assert any("Arguments:" in message and "method" in message for message in outputs)
    assert not errors
