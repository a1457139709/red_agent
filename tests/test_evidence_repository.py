from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from models.evidence import Evidence
from storage.repositories.evidence import EvidenceRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_evidence_repository_round_trips_captured_metadata(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    repository = EvidenceRepository(SQLiteStorage(settings.sqlite_path))

    operation = operation_service.create_operation(title="Collect", objective="Capture proof")
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    evidence = Evidence.create(
        operation_id=operation.id,
        job_id=job.id,
        evidence_type="response_headers",
        target_ref=job.target_ref,
        title="Homepage headers",
        summary="Captured server response headers.",
        artifact_path=".red-code/operations/op-1/evidence/headers.json",
        content_type="application/json",
        hash_digest="sha256:abc123",
        captured_at="2026-04-03T12:00:00+00:00",
    )

    repository.create(evidence)
    loaded = repository.get(evidence.public_id)

    assert loaded is not None
    assert loaded.id == evidence.id
    assert loaded.captured_at == "2026-04-03T12:00:00+00:00"
    assert loaded.summary == "Captured server response headers."
    assert loaded.content_type == "application/json"
