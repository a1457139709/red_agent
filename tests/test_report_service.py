import json

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_service import OperationService
from app.report_service import ReportService
from app.session_service import SessionService
from models.operation import OperationStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_report_service_writes_session_owned_report_files_and_links(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    session_service = SessionService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    report_service = ReportService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Reports",
        objective="Generate report output",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=OperationStatus.READY,
    )
    session = session_service.require_session(operation.id)
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    artifact = artifact_service.create_artifact(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured a response.",
        artifact_path="artifacts/http_response.json",
    )
    finding = finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Service is reachable.",
    )

    report = report_service.create_report(
        operation_identifier=operation.public_id,
        report_type="artifact_index",
        title="Artifact index",
        summary="Summarize session artifacts.",
        artifact_identifiers=[artifact.public_id],
        finding_identifiers=[finding.public_id],
        output_payload={"ok": True},
    )

    output_path = settings.sessions_dir / session.public_id / (report.artifact_path or "")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.exists()
    assert "reports" in str(output_path)
    assert payload == {"ok": True}
    assert len(report_service.list_artifact_links(report.public_id)) == 1
    assert len(report_service.list_finding_links(report.public_id)) == 1
