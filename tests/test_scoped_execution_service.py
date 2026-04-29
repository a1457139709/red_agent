from agent.settings import Settings
from app.job_service import JobService
from app.scoped_execution_service import ScopedExecutionService
from app.session_event_service import SessionEventService
from conftest import create_redteam_operation
from models.job import JobStatus
from models.session import SessionStatus
from models.session_event import SessionEventLevel, SessionEventType
from orchestration.scope_validator import AdmissionRequest


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def make_request(*, session_id: str, job_id: str | None, raw_target: str, tool_name: str = "http_probe"):
    return AdmissionRequest(
        session_id=session_id,
        job_id=job_id,
        tool_name=tool_name,
        tool_category="recon",
        raw_target=raw_target,
        protocol="https" if raw_target.startswith("https://") else None,
    )


def test_scoped_execution_service_blocks_out_of_scope_requests_without_mutating_job_state(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        status=SessionStatus.ACTIVE,
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://outside.example.org",
    )

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://outside.example.org",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    events = event_service.list_events(operation.public_id)
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "blocked"
    assert refreshed.status == JobStatus.PENDING
    assert [event.event_type for event in events] == [
        SessionEventType.ADMISSION_DENIED,
        SessionEventType.ADMISSION_REQUESTED,
    ]


def test_scoped_execution_service_records_full_confirmation_and_success_flow(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        confirmation_required_actions=["http_probe"],
        status=SessionStatus.ACTIVE,
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
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
    assert refreshed.status == JobStatus.PENDING
    assert [event.event_type for event in events] == [
        SessionEventType.EXECUTION_SUCCEEDED,
        SessionEventType.EXECUTION_STARTED,
        SessionEventType.ADMISSION_REQUESTED,
        SessionEventType.CONFIRMATION_APPROVED,
        SessionEventType.CONFIRMATION_REQUIRED,
        SessionEventType.ADMISSION_REQUESTED,
    ]
    assert events[2].payload["admission_stage"] == "post_confirmation_recheck"


def test_scoped_execution_service_records_execution_failure_without_mutating_job_state(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        status=SessionStatus.ACTIVE,
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    events = event_service.list_events(operation.public_id)
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "failed"
    assert refreshed.status == JobStatus.PENDING
    assert events[0].event_type == SessionEventType.EXECUTION_FAILED
    assert events[1].event_type == SessionEventType.EXECUTION_STARTED


def test_scoped_execution_service_enforces_rate_limit_from_recent_execution_events(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        rate_limit_per_minute=1,
        status=SessionStatus.ACTIVE,
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    event_service.create_event(
        session_identifier=operation.public_id,
        event_type=SessionEventType.EXECUTION_STARTED,
        level=SessionEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    refreshed = job_service.require_job(job.public_id)
    events = event_service.list_events(operation.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "rate_limit_exceeded"
    assert refreshed.status == JobStatus.PENDING
    assert events[0].event_type == SessionEventType.ADMISSION_DENIED


def test_scoped_execution_service_rechecks_rate_limit_after_confirmation(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        confirmation_required_actions=["http_probe"],
        rate_limit_per_minute=1,
        status=SessionStatus.ACTIVE,
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    def confirm(_prompt):
        event_service.create_event(
            session_identifier=operation.public_id,
            event_type=SessionEventType.EXECUTION_STARTED,
            level=SessionEventLevel.INFO,
            tool_name="http_probe",
            tool_category="recon",
            target_ref="https://example.com",
        )
        return True

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
        confirm=confirm,
    )

    refreshed = job_service.require_job(job.public_id)
    events = event_service.list_events(operation.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "rate_limit_exceeded"
    assert refreshed.status == JobStatus.PENDING
    assert [event.event_type for event in events] == [
        SessionEventType.ADMISSION_DENIED,
        SessionEventType.ADMISSION_REQUESTED,
        SessionEventType.CONFIRMATION_APPROVED,
        SessionEventType.EXECUTION_STARTED,
        SessionEventType.CONFIRMATION_REQUIRED,
        SessionEventType.ADMISSION_REQUESTED,
    ]
    assert events[1].payload["admission_stage"] == "post_confirmation_recheck"


def test_scoped_execution_service_enforces_max_concurrency_before_execution(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
        max_concurrency=1,
        status=SessionStatus.ACTIVE,
    )
    running_job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        status=JobStatus.RUNNING,
    )
    blocked_job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    assert running_job.status == JobStatus.RUNNING

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
            job_id=blocked_job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    refreshed = job_service.require_job(blocked_job.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "max_concurrency_exceeded"
    assert refreshed.status == JobStatus.PENDING


def test_scoped_execution_service_blocks_non_runnable_operation_statuses(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    execution_service = ScopedExecutionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Draft Recon",
        objective="Inspect public web surface",
        allowed_domains=["example.com"],
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    result = execution_service.execute(
        request=make_request(
            session_id=operation.public_id,
            job_id=job.public_id,
            raw_target="https://example.com",
        ),
        executor=lambda _request, _target: {"ok": True},
    )

    refreshed = job_service.require_job(job.public_id)
    events = event_service.list_events(operation.public_id)

    assert result.status == "blocked"
    assert result.decision.reason_code == "session_not_runnable"
    assert refreshed.status == JobStatus.PENDING
    assert [event.event_type for event in events] == [
        SessionEventType.ADMISSION_DENIED,
        SessionEventType.ADMISSION_REQUESTED,
    ]
