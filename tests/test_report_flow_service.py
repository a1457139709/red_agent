from pathlib import Path
import json

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.report_flow_service import ReportFlowService
from app.session_service import SessionService
from conftest import create_redteam_operation
from models.operation import OperationStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def seed_reporting_session(settings):
    session_service = SessionService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    flow_service = ReportFlowService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Report Flow",
        objective="Generate report flow outputs",
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
        session_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured a response.",
        artifact_path="artifacts/http_response.json",
    )
    finding = finding_service.create_finding(
        session_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Service is reachable.",
    )
    finding_service.link_artifacts(finding.public_id, [artifact.public_id])

    return {
        "flow_service": flow_service,
        "session": session,
        "artifact": artifact,
        "finding": finding,
    }


def _load_report_payload(settings: Settings, session_id: str, relative_path: str):
    output_path = settings.sessions_dir / session_id / relative_path
    suffix = Path(relative_path).suffix
    text = output_path.read_text(encoding="utf-8")
    return output_path, text if suffix == ".md" else json.loads(text)


def test_report_flow_service_reuses_existing_session_summary_report(tmp_path):
    settings = build_settings(tmp_path)
    seeded = seed_reporting_session(settings)
    flow_service = seeded["flow_service"]
    session = seeded["session"]

    first = flow_service.get_or_create_session_summary(session.public_id)
    second = flow_service.get_or_create_session_summary(session.public_id)
    output_path, payload = _load_report_payload(settings, session.id, first.report.artifact_path or "")

    assert not first.reused
    assert second.reused
    assert second.report.public_id == first.report.public_id
    assert output_path.exists()
    assert payload["session"]["public_id"] == session.public_id
    assert payload["counts"]["artifacts"] == 1
    assert first.linked_artifact_ids == [seeded["artifact"].public_id]
    assert first.linked_finding_ids == [seeded["finding"].public_id]


def test_report_flow_service_generates_findings_summary_with_traceable_links(tmp_path):
    settings = build_settings(tmp_path)
    seeded = seed_reporting_session(settings)
    flow_service = seeded["flow_service"]
    session = seeded["session"]
    artifact = seeded["artifact"]
    finding = seeded["finding"]

    result = flow_service.get_or_create_findings_summary(session.public_id)
    output_path, payload = _load_report_payload(settings, session.id, result.report.artifact_path or "")

    assert not result.reused
    assert output_path.exists()
    assert payload["session"]["public_id"] == session.public_id
    assert payload["counts"]["findings"] == 1
    assert payload["findings"][0]["finding_id"] == finding.public_id
    assert payload["findings"][0]["artifact_public_ids"] == [artifact.public_id]
    assert result.linked_artifact_ids == [artifact.public_id]
    assert result.linked_finding_ids == [finding.public_id]


def test_report_flow_service_generates_operator_report_as_markdown(tmp_path):
    settings = build_settings(tmp_path)
    seeded = seed_reporting_session(settings)
    flow_service = seeded["flow_service"]
    session = seeded["session"]

    result = flow_service.get_or_create_operator_report(session.public_id)
    output_path, payload = _load_report_payload(settings, session.id, result.report.artifact_path or "")

    assert not result.reused
    assert output_path.suffix == ".md"
    assert "# Operator Report:" in payload
    assert f"Session: {session.public_id}" in payload
    assert "## Findings" in payload
    assert "## Artifacts" in payload
