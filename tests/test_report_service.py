import inspect
import json

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.report_service import ReportCreationError, ReportService
from app.session_service import SessionService
from conftest import create_redteam_operation
from models.session import SessionStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_report_service_writes_session_owned_report_files_and_links(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    report_service = ReportService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Reports",
        objective="Generate report output",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=SessionStatus.ACTIVE,
    )
    session = session_service.require_session(operation.id)
    job = job_service.create_job(
        session_identifier=session.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    artifact = artifact_service.create_artifact(
        session_identifier=session.public_id,
        source_job_identifier=job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured a response.",
        artifact_path="artifacts/http_response.json",
    )
    finding = finding_service.create_finding(
        session_identifier=session.public_id,
        source_job_identifier=job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Service is reachable.",
    )

    report = report_service.create_report(
        session_identifier=session.public_id,
        report_type="artifact_index",
        title="Artifact index",
        summary="Summarize session artifacts.",
        artifact_identifiers=[artifact.public_id],
        finding_identifiers=[finding.public_id],
        output_payload={"ok": True},
    )

    output_path = settings.sessions_dir / session.id / (report.artifact_path or "")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.exists()
    assert "reports" in str(output_path)
    assert report.id in output_path.name
    assert payload == {"ok": True}
    assert len(report_service.list_artifact_links(report.public_id)) == 1
    assert len(report_service.list_finding_links(report.public_id)) == 1


def test_report_service_rolls_back_failed_creation_and_exposes_ai_prompt(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    report_service = ReportService.from_settings(settings)

    first_operation = create_redteam_operation(
        settings,
        title="Primary",
        objective="Primary session",
        allowed_hosts=["one.example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=SessionStatus.ACTIVE,
    )
    second_operation = create_redteam_operation(
        settings,
        title="Secondary",
        objective="Secondary session",
        allowed_hosts=["two.example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=SessionStatus.ACTIVE,
    )
    first_session = session_service.require_session(first_operation.id)
    second_session = session_service.require_session(second_operation.id)
    second_job = job_service.create_job(
        session_identifier=second_session.public_id,
        job_type="http_probe",
        target_ref="https://two.example.com",
    )
    foreign_artifact = artifact_service.create_artifact(
        session_identifier=second_session.public_id,
        source_job_identifier=second_job.public_id,
        artifact_type="http_response",
        target_ref="https://two.example.com",
        title="HTTP response",
        summary="Captured a response.",
        artifact_path="artifacts/http_response.json",
    )

    try:
        report_service.create_report(
            session_identifier=first_session.public_id,
            report_type="artifact_index",
            title="Artifact index",
            summary="This should fail.",
            artifact_identifiers=[foreign_artifact.public_id],
            output_payload={"ok": True},
        )
    except ReportCreationError as exc:
        assert "Report creation failed:" in str(exc)
        assert "same session" in str(exc)
        assert "Artifact identifiers" in exc.ai_prompt
        assert exc.ai_context["artifact_identifiers"] == [foreign_artifact.public_id]
    else:
        raise AssertionError("Expected report creation failure for cross-session artifact.")

    reports_dir = settings.sessions_dir / first_session.id / "reports"
    reports = report_service.list_reports(first_session.public_id)

    assert reports == []
    assert not reports_dir.exists() or list(reports_dir.iterdir()) == []


def test_report_service_exposes_session_only_report_input():
    signature = inspect.signature(ReportService.create_report)
    source = inspect.getsource(ReportService)

    assert "session_identifier" in signature.parameters
    assert "operation_identifier" not in signature.parameters
    assert "OperationRepository" not in source
    assert "resolve_session_identifier" not in source
