from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from conftest import create_redteam_operation


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_redteam_public_ids_increment_by_entity_family(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)

    first_operation = create_redteam_operation(settings, title="First", objective="One")
    second_operation = create_redteam_operation(settings, title="Second", objective="Two")

    first_job = job_service.create_job(
        session_identifier=first_operation.public_id,
        job_type="dns_lookup",
        target_ref="example.com",
    )
    second_job = job_service.create_job(
        session_identifier=first_operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    first_artifact = artifact_service.create_artifact(
        session_identifier=first_operation.public_id,
        source_job_identifier=first_job.public_id,
        artifact_type="dns_answer",
        target_ref="example.com",
        title="A record",
        summary="Captured DNS A record.",
    )
    second_artifact = artifact_service.create_artifact(
        session_identifier=first_operation.public_id,
        source_job_identifier=second_job.public_id,
        artifact_type="response_headers",
        target_ref="https://example.com",
        title="Headers",
        summary="Captured HTTP headers.",
    )

    first_finding = finding_service.create_finding(
        session_identifier=first_operation.public_id,
        source_job_identifier=first_job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="example.com:80",
        severity="low",
        confidence="medium",
    )
    second_finding = finding_service.create_finding(
        session_identifier=second_operation.public_id,
        finding_type="weak_tls",
        title="Weak TLS",
        target_ref="example.com:443",
        severity="medium",
        confidence="high",
    )

    assert first_operation.public_id == "S0001"
    assert second_operation.public_id == "S0002"
    assert first_job.public_id == "J0001"
    assert second_job.public_id == "J0002"
    assert first_artifact.public_id == "A0001"
    assert second_artifact.public_id == "A0002"
    assert first_finding.public_id == "F0001"
    assert second_finding.public_id == "F0002"
