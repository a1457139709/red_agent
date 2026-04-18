import sqlite3

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.job_service import JobService
from app.operation_service import OperationService
from models.operation import OperationStatus
from storage.repositories.artifacts import ARTIFACTS_SCHEMA


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

    assert artifact.public_id == "A0001"
    assert stored.session_id == operation.id
    assert stored.operation_id == operation.id
    assert stored.source_job_id == job.id
    assert stored.job_id == job.id
    assert listed[0].id == artifact.id


def test_artifact_service_migrates_legacy_e_public_ids_to_a_prefix(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Legacy artifacts",
        objective="Migrate E-prefixed artifact ids",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=OperationStatus.READY,
    )

    with sqlite3.connect(settings.sqlite_path) as connection:
        connection.executescript(ARTIFACTS_SCHEMA)
        connection.execute(
            """
            INSERT INTO artifacts (
                id, public_id, session_id, source_job_id, artifact_type, target_ref, title,
                summary, artifact_path, content_type, hash_digest, captured_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "artifact-legacy-1",
                "E0001",
                operation.id,
                None,
                "http_response",
                "https://example.com",
                "Legacy artifact",
                "Stored before the Phase 6 rename.",
                "artifacts/legacy.json",
                "application/json",
                "sha256:legacy",
                "2026-04-17T09:00:00+00:00",
                "{}",
            ),
        )
        connection.commit()

    artifact_service = ArtifactService.from_settings(settings)

    loaded = artifact_service.require_artifact("A0001")
    listed = artifact_service.list_artifacts(operation.public_id, limit=None)

    assert loaded.id == "artifact-legacy-1"
    assert loaded.public_id == "A0001"
    assert [artifact.public_id for artifact in listed] == ["A0001"]

    with sqlite3.connect(settings.sqlite_path) as connection:
        row = connection.execute(
            "SELECT public_id FROM artifacts WHERE id = ?",
            ("artifact-legacy-1",),
        ).fetchone()

    assert row is not None
    assert row[0] == "A0001"


def test_artifact_service_migrates_mixed_public_ids_into_stable_a_sequence(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Mixed artifacts",
        objective="Normalize mixed artifact ids",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=OperationStatus.READY,
    )

    with sqlite3.connect(settings.sqlite_path) as connection:
        connection.executescript(ARTIFACTS_SCHEMA)
        connection.executemany(
            """
            INSERT INTO artifacts (
                id, public_id, session_id, source_job_id, artifact_type, target_ref, title,
                summary, artifact_path, content_type, hash_digest, captured_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "artifact-e-2",
                    "E0002",
                    operation.id,
                    None,
                    "http_response",
                    "https://example.com/two",
                    "Legacy two",
                    "Second legacy artifact.",
                    "artifacts/two.json",
                    "application/json",
                    "sha256:two",
                    "2026-04-17T10:00:00+00:00",
                    "{}",
                ),
                (
                    "artifact-a-5",
                    "A0005",
                    operation.id,
                    None,
                    "http_response",
                    "https://example.com/five",
                    "Already renamed",
                    "Artifact with a future A id.",
                    "artifacts/five.json",
                    "application/json",
                    "sha256:five",
                    "2026-04-17T11:00:00+00:00",
                    "{}",
                ),
                (
                    "artifact-e-1",
                    "E0001",
                    operation.id,
                    None,
                    "http_response",
                    "https://example.com/one",
                    "Legacy one",
                    "First legacy artifact.",
                    "artifacts/one.json",
                    "application/json",
                    "sha256:one",
                    "2026-04-17T09:00:00+00:00",
                    "{}",
                ),
            ],
        )
        connection.commit()

    artifact_service = ArtifactService.from_settings(settings)

    first_pass = {
        artifact.id: artifact.public_id
        for artifact in artifact_service.list_artifacts(operation.public_id, limit=None)
    }
    second_pass = {
        artifact.id: artifact.public_id
        for artifact in ArtifactService.from_settings(settings).list_artifacts(
            operation.public_id,
            limit=None,
        )
    }

    assert first_pass == {
        "artifact-a-5": "A0003",
        "artifact-e-2": "A0002",
        "artifact-e-1": "A0001",
    }
    assert second_pass == first_pass
