from agent.settings import Settings
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.operation_service import OperationService
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
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)

    operation = operation_service.create_operation(title="Assess", objective="Review evidence")
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    evidence = evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        evidence_type="http_response",
        target_ref="https://example.com",
        title="Homepage response",
        summary="Captured homepage response.",
    )
    finding = finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="interesting_header",
        title="Interesting header observed",
        target_ref="https://example.com",
        severity="low",
        confidence="medium",
        summary="Header suggests a framework.",
    )

    links = finding_service.link_evidence(finding.public_id, [evidence.public_id])
    confirmed = finding_service.confirm_finding(finding.public_id)
    dismissed = finding_service.dismiss_finding(finding.public_id, reason="Accepted behavior.")
    evidence_links = finding_service.list_evidence_links_for_finding(finding.public_id)
    finding_links = finding_service.list_finding_links_for_evidence(evidence.public_id)

    assert len(links) == 1
    assert confirmed.status == FindingStatus.CONFIRMED
    assert dismissed.status == FindingStatus.DISMISSED
    assert "Accepted behavior." in dismissed.next_action
    assert evidence_links[0].evidence_id == evidence.id
    assert finding_links[0].finding_id == finding.id
