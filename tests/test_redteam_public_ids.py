from agent.settings import Settings
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_service import OperationService


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_redteam_public_ids_increment_by_entity_family(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)

    first_operation = operation_service.create_operation(title="First", objective="One")
    second_operation = operation_service.create_operation(title="Second", objective="Two")

    first_job = job_service.create_job(
        operation_identifier=first_operation.public_id,
        job_type="dns_lookup",
        target_ref="example.com",
    )
    second_job = job_service.create_job(
        operation_identifier=first_operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    first_evidence = evidence_service.create_evidence(
        operation_identifier=first_operation.public_id,
        job_identifier=first_job.public_id,
        evidence_type="dns_answer",
        target_ref="example.com",
        title="A record",
        summary="Captured DNS A record.",
    )
    second_evidence = evidence_service.create_evidence(
        operation_identifier=first_operation.public_id,
        job_identifier=second_job.public_id,
        evidence_type="response_headers",
        target_ref="https://example.com",
        title="Headers",
        summary="Captured HTTP headers.",
    )

    first_finding = finding_service.create_finding(
        operation_identifier=first_operation.public_id,
        source_job_identifier=first_job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="example.com:80",
        severity="low",
        confidence="medium",
    )
    second_finding = finding_service.create_finding(
        operation_identifier=second_operation.public_id,
        finding_type="weak_tls",
        title="Weak TLS",
        target_ref="example.com:443",
        severity="medium",
        confidence="high",
    )

    assert first_operation.public_id == "O0001"
    assert second_operation.public_id == "O0002"
    assert first_job.public_id == "J0001"
    assert second_job.public_id == "J0002"
    assert first_evidence.public_id == "E0001"
    assert second_evidence.public_id == "E0002"
    assert first_finding.public_id == "F0001"
    assert second_finding.public_id == "F0002"
