from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from models.evidence import Evidence
from models.finding import Finding
from models.finding_evidence_link import FindingEvidenceLink
from storage.repositories.evidence import EvidenceRepository
from storage.repositories.finding_evidence_links import FindingEvidenceLinkRepository
from storage.repositories.findings import FindingRepository
from storage.repositories.jobs import JobRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_finding_evidence_link_repository_supports_bidirectional_traceability(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    JobRepository(storage)
    evidence_repository = EvidenceRepository(storage)
    finding_repository = FindingRepository(storage)
    link_repository = FindingEvidenceLinkRepository(storage)

    operation = operation_service.create_operation(title="Trace", objective="Link evidence")
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    first_evidence = evidence_repository.create(
        Evidence.create(
            operation_id=operation.id,
            job_id=job.id,
            evidence_type="http_response",
            target_ref="https://example.com",
            title="Response",
            summary="Response summary",
        )
    )
    second_evidence = evidence_repository.create(
        Evidence.create(
            operation_id=operation.id,
            job_id=job.id,
            evidence_type="http_headers",
            target_ref="https://example.com",
            title="Headers",
            summary="Header summary",
        )
    )
    finding = finding_repository.create(
        Finding.create(
            operation_id=operation.id,
            source_job_id=job.id,
            finding_type="header_leak",
            title="Header leak",
            target_ref="https://example.com",
            severity="low",
            confidence="medium",
        )
    )

    link_repository.create(
        FindingEvidenceLink.create(
            operation_id=operation.id,
            finding_id=finding.id,
            evidence_id=first_evidence.id,
        )
    )
    link_repository.create(
        FindingEvidenceLink.create(
            operation_id=operation.id,
            finding_id=finding.id,
            evidence_id=second_evidence.id,
        )
    )

    assert len(link_repository.list(operation.id)) == 2
    assert len(link_repository.list_for_finding(finding.id)) == 2
    assert len(link_repository.list_for_evidence(first_evidence.id)) == 1
