from agent.settings import Settings
from app.job_service import JobService
from app.operation_event_service import OperationEventService
from app.operation_service import OperationService
from models.operation_event import OperationEventLevel, OperationEventType


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_operation_event_service_persists_lists_and_counts_events(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)

    operation = operation_service.create_operation(title="Recon", objective="Inspect scope")
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    event_service.create_event(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        event_type=OperationEventType.ADMISSION_REQUESTED,
        level=OperationEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Requested",
        created_at="2026-04-03T08:00:00+00:00",
    )
    event_service.create_event(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        event_type=OperationEventType.EXECUTION_STARTED,
        level=OperationEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Started",
        created_at="2026-04-03T08:00:10+00:00",
    )

    events = event_service.list_events(operation.public_id)
    recent_count = event_service.count_events_since(
        operation.public_id,
        event_type=OperationEventType.EXECUTION_STARTED,
        since="2026-04-03T08:00:05+00:00",
    )

    assert [event.message for event in events] == ["Started", "Requested"]
    assert events[0].job_id == job.id
    assert recent_count == 1
