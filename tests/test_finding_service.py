from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from conftest import create_redteam_operation
from models.finding import FindingStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_finding_service_supports_confirmation_dismissal_and_traceability(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)

    operation = create_redteam_operation(settings, title="Assess", objective="Review evidence")
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
        title="Homepage response",
        summary="Captured homepage response.",
    )
    finding = finding_service.create_finding(
        session_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="interesting_header",
        title="Interesting header observed",
        target_ref="https://example.com",
        severity="low",
        confidence="medium",
        summary="Header suggests a framework.",
    )

    links = finding_service.link_artifacts(finding.public_id, [artifact.public_id])
    confirmed = finding_service.confirm_finding(finding.public_id)
    dismissed = finding_service.dismiss_finding(finding.public_id, reason="Accepted behavior.")
    artifact_links = finding_service.list_artifact_links_for_finding(finding.public_id)
    finding_links = finding_service.list_finding_links_for_artifact(artifact.public_id)

    assert len(links) == 1
    assert confirmed.status == FindingStatus.CONFIRMED
    assert dismissed.status == FindingStatus.DISMISSED
    assert "Accepted behavior." in dismissed.next_action
    assert artifact_links[0].artifact_id == artifact.id
    assert finding_links[0].finding_id == finding.id
