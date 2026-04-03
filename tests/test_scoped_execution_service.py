from agent.settings import Settings
from app.job_service import JobService
from app.operation_event_service import OperationEventService
from app.operation_service import OperationService
from app.scoped_execution_service import ScopedExecutionService
from models.job import JobStatus
from models.operation import OperationStatus
from models.operation_event import OperationEventLevel, OperationEventType
from orchestration.scope_validator import AdmissionRequest


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def make_request(*, operation_id: str, job_id: str | None, raw_target: str, tool_name: str = "http_probe"):
    return AdmissionRequest(
        operation_id=operation_id,
        job_id=job_id,
        tool_name=tool_name,
        tool_category="recon",
        raw_target=raw_target,
        protocol="https" if raw_target.startswith("https://") else None,
    )


def test_scoped_execution_service_blocks_out_of_scope_requests_and_updates_job(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://outside.example.org",
    )

    result = execution_service.execute(
        request=make_request(
            operation_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://outside.example.org",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    events = event_service.list_events(operation.public_id)
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "blocked"
    assert refreshed.status == JobStatus.BLOCKED
    assert [event.event_type for event in events] == [
        OperationEventType.ADMISSION_DENIED,
        OperationEventType.ADMISSION_REQUESTED,
    ]


def test_scoped_execution_service_records_full_confirmation_and_success_flow(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        confirmation_required_actions=["http_probe"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            operation_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, target: {"target": target.normalized_target},
        confirm=lambda prompt: "https://example.com" in prompt,
    )

    events = event_service.list_events(operation.public_id)
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "succeeded"
    assert result.result == {"target": "https://example.com"}
    assert refreshed.status == JobStatus.SUCCEEDED
    assert [event.event_type for event in events] == [
        OperationEventType.EXECUTION_SUCCEEDED,
        OperationEventType.EXECUTION_STARTED,
        OperationEventType.CONFIRMATION_APPROVED,
        OperationEventType.CONFIRMATION_REQUIRED,
        OperationEventType.ADMISSION_REQUESTED,
    ]


def test_scoped_execution_service_marks_job_failed_and_persists_execution_failure(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            operation_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    events = event_service.list_events(operation.public_id)
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "failed"
    assert refreshed.status == JobStatus.FAILED
    assert events[0].event_type == OperationEventType.EXECUTION_FAILED
    assert events[1].event_type == OperationEventType.EXECUTION_STARTED


def test_scoped_execution_service_enforces_rate_limit_from_recent_execution_events(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        rate_limit_per_minute=1,
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    event_service.create_event(
        operation_identifier=operation.public_id,
        event_type=OperationEventType.EXECUTION_STARTED,
        level=OperationEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            operation_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    refreshed = job_service.require_job(job.public_id)
    events = event_service.list_events(operation.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "rate_limit_exceeded"
    assert refreshed.status == JobStatus.BLOCKED
    assert events[0].event_type == OperationEventType.ADMISSION_DENIED


def test_scoped_execution_service_enforces_max_concurrency_before_execution(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        max_concurrency=1,
        status=OperationStatus.READY,
    )
    running_job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        status=JobStatus.RUNNING,
    )
    blocked_job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    assert running_job.status == JobStatus.RUNNING

    result = execution_service.execute(
        request=make_request(
            operation_id=operation.public_id,
            job_id=blocked_job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    refreshed = job_service.require_job(blocked_job.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "max_concurrency_exceeded"
    assert refreshed.status == JobStatus.BLOCKED


def test_scoped_execution_service_blocks_non_runnable_operation_statuses(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Draft Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            operation_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    refreshed = job_service.require_job(job.public_id)
    events = event_service.list_events(operation.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "operation_not_runnable"
    assert refreshed.status == JobStatus.BLOCKED
    assert [event.event_type for event in events] == [
        OperationEventType.ADMISSION_DENIED,
        OperationEventType.ADMISSION_REQUESTED,
    ]
