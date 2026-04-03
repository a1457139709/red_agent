from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from models.job import JobLogLevel


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_job_service_creates_lists_and_loads_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)

    operation = operation_service.create_operation(title="Surface recon", objective="Map services")
    first = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="dns_lookup",
        target_ref="example.com",
        arguments={"record_type": "A"},
        retry_limit=1,
    )
    second = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        dependency_job_ids=[first.public_id],
        timeout_seconds=30,
    )

    jobs = job_service.list_jobs(operation.public_id)
    loaded = job_service.get_job(second.public_id)

    assert [job.id for job in jobs] == [second.id, first.id]
    assert loaded is not None
    assert loaded.id == second.id
    assert loaded.dependency_job_ids == [first.id]
    assert loaded.arguments == {}
    assert loaded.timeout_seconds == 30


def test_job_service_writes_and_reads_job_logs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)

    operation = operation_service.create_operation(title="Probe", objective="Inspect endpoint")
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    entry = job_service.write_log(
        job_identifier=job.public_id,
        level=JobLogLevel.INFO,
        message="job_created",
        payload={"target_ref": job.target_ref},
    )
    logs = job_service.list_logs(job.public_id)

    assert entry.job_id == job.id
    assert logs[0].message == "job_created"
    assert logs[0].payload["target_ref"] == "https://example.com"
