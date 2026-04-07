from agent.settings import Settings
from app.dashboard_service import DashboardService
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_event_service import OperationEventService
from app.operation_service import OperationService
from models.job import JobStatus
from models.operation import OperationStatus
from models.operation_event import OperationEventLevel, OperationEventType


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_dashboard_service_aggregates_counts_and_recent_items(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)
    event_service = OperationEventService.from_settings(settings)
    dashboard_service = DashboardService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect dashboard",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=OperationStatus.READY,
    )
    failed_job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    failed_job.status = JobStatus.FAILED
    failed_job.last_error = "probe failed"
    job_service.save_job(failed_job)

    evidence = evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=failed_job.public_id,
        evidence_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response.",
    )
    finding = finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=failed_job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Service exposed.",
    )
    finding_service.link_evidence(finding.public_id, [evidence.public_id])
    event_service.create_event(
        operation_identifier=operation.public_id,
        job_identifier=failed_job.public_id,
        event_type=OperationEventType.ADMISSION_DENIED,
        level=OperationEventLevel.ERROR,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Denied.",
    )

    dashboard = dashboard_service.build_dashboard(operation.public_id)

    assert dashboard.operation.id == operation.id
    assert dashboard.job_counts["failed"] == 1
    assert dashboard.finding_counts["open"] == 1
    assert dashboard.evidence_count == 1
    assert dashboard.flagged_jobs[0].id == failed_job.id
    assert dashboard.recent_findings[0].id == finding.id
    assert dashboard.recent_evidence[0].id == evidence.id
    assert dashboard.event_counts["admission_denied"] == 1
