from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.job_service import JobService
from app.operation_service import OperationService
from models.operation import OperationStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_artifact_service_persists_session_owned_artifacts(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Artifacts",
        objective="Persist raw session output",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=OperationStatus.READY,
    )
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
        content_type="application/json",
        hash_digest="abc123",
    )

    stored = artifact_service.require_artifact(artifact.public_id)
    listed = artifact_service.list_artifacts(operation.public_id, limit=None)

    assert stored.session_id == operation.id
    assert stored.operation_id == operation.id
    assert stored.source_job_id == job.id
    assert stored.job_id == job.id
    assert listed[0].id == artifact.id
