from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.dashboard_service import DashboardService
from app.finding_service import FindingService
from app.job_service import JobService
from app.session_service import SessionService
from app.session_event_service import SessionEventService
from conftest import create_redteam_bundle, create_redteam_operation
from models.job import JobStatus
from models.session import SessionStatus
from models.session_event import SessionEventLevel, SessionEventType


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_dashboard_service_aggregates_counts_and_recent_items(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    dashboard_service = DashboardService.from_settings(settings)
    session_service = SessionService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Recon",
        objective="Inspect dashboard",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=SessionStatus.ACTIVE,
    )
    failed_job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    failed_job.status = JobStatus.FAILED
    failed_job.last_error = "probe failed"
    job_service.save_job(failed_job)

    artifact = artifact_service.create_artifact(
        session_identifier=operation.public_id,
        source_job_identifier=failed_job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response.",
    )
    finding = finding_service.create_finding(
        session_identifier=operation.public_id,
        source_job_identifier=failed_job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Service exposed.",
    )
    finding_service.link_artifacts(finding.public_id, [artifact.public_id])
    event_service.create_event(
        session_identifier=operation.public_id,
        job_identifier=failed_job.public_id,
        event_type=SessionEventType.ADMISSION_DENIED,
        level=SessionEventLevel.ERROR,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Denied.",
    )

    session = session_service.require_session(operation.id)
    dashboard = dashboard_service.build_dashboard(session.public_id)

    assert dashboard.session.id == operation.id
    assert dashboard.job_counts["failed"] == 1
    assert dashboard.finding_counts["open"] == 1
    assert dashboard.artifact_count == 1
    assert dashboard.flagged_jobs[0].id == failed_job.id
    assert dashboard.recent_findings[0].id == finding.id
    assert dashboard.recent_artifacts[0].id == artifact.id
    assert dashboard.event_counts["admission_denied"] == 1


def test_dashboard_service_defaults_to_most_recent_runtime_activity(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    dashboard_service = DashboardService.from_settings(settings)
    session_service = SessionService.from_settings(settings)

    newer_but_idle = create_redteam_bundle(
        settings,
        title="Idle",
        objective="No activity",
        status=SessionStatus.ACTIVE,
    ).session
    active = create_redteam_bundle(
        settings,
        title="Active",
        objective="Recent event",
        status=SessionStatus.ACTIVE,
    ).session

    active_job = job_service.create_job(
        session_identifier=active.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    event_service.create_event(
        session_identifier=active.public_id,
        job_identifier=active_job.public_id,
        event_type=SessionEventType.EXECUTION_FAILED,
        level=SessionEventLevel.ERROR,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Recent failure.",
        created_at="2026-04-08T10:00:00+00:00",
    )

    idle_loaded = session_service.require_session(newer_but_idle.public_id)
    idle_loaded.updated_at = "2026-04-08T09:00:00+00:00"
    session_service.save_session(idle_loaded)

    active_loaded = session_service.require_session(active.public_id)
    active_loaded.updated_at = "2026-04-08T08:00:00+00:00"
    session_service.save_session(active_loaded)

    dashboard = dashboard_service.build_dashboard()

    assert dashboard.session.id == active.id
