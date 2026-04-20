import pytest

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.evidence_service import EvidenceService
from app.job_service import JobService
from conftest import create_redteam_operation


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_evidence_service_warns_on_legacy_create_write_path(tmp_path):
    settings = build_settings(tmp_path)
    job_service = JobService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)

    operation = create_redteam_operation(settings, title="Assess", objective="Exercise legacy evidence")
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )

    with pytest.warns(
        DeprecationWarning,
        match="EvidenceService.create_evidence\\(\\) is deprecated as a primary write path",
    ):
        evidence = evidence_service.create_evidence(
            operation_identifier=operation.public_id,
            job_identifier=job.public_id,
            evidence_type="http_response",
            target_ref="https://example.com",
            title="Homepage response",
            summary="Captured homepage response.",
        )

    assert evidence.public_id == "A0001"
    assert evidence.operation_id == operation.id
    assert evidence.job_id == job.id


def test_evidence_service_warns_on_legacy_save_write_path(tmp_path):
    settings = build_settings(tmp_path)
    artifact_service = ArtifactService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)

    operation = create_redteam_operation(settings, title="Assess", objective="Save legacy evidence")
    artifact = artifact_service.create_artifact(
        session_identifier=operation.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="Homepage response",
        summary="Captured homepage response.",
    )
    evidence = evidence_service.require_evidence(artifact.public_id)
    evidence.summary = "Updated through the compatibility wrapper."

    with pytest.warns(
        DeprecationWarning,
        match="EvidenceService.save_evidence\\(\\) is deprecated as a primary write path",
    ):
        saved = evidence_service.save_evidence(evidence)

    assert saved.summary == "Updated through the compatibility wrapper."
    assert artifact_service.require_artifact(saved.public_id).summary == saved.summary


def test_evidence_service_read_paths_remain_available(tmp_path):
    settings = build_settings(tmp_path)
    artifact_service = ArtifactService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)

    operation = create_redteam_operation(settings, title="Assess", objective="Read compatibility evidence")
    artifact = artifact_service.create_artifact(
        session_identifier=operation.public_id,
        artifact_type="dns_answer",
        target_ref="example.com",
        title="A record",
        summary="Captured DNS answer.",
    )

    loaded = evidence_service.require_evidence(artifact.public_id)
    listed = evidence_service.list_evidence(operation.public_id, limit=None)

    assert loaded.public_id == artifact.public_id
    assert [item.public_id for item in listed] == [artifact.public_id]
