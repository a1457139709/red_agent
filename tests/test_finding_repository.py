from agent.settings import Settings
from app.operation_service import OperationService
from models.finding import Finding, FindingStatus
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


def test_finding_repository_persists_status_and_confidence_fields(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    storage = SQLiteStorage(settings.sqlite_path)
    JobRepository(storage)
    repository = FindingRepository(storage)

    operation = operation_service.create_operation(title="Assess", objective="Review results")
    finding = Finding.create(
        operation_id=operation.id,
        finding_type="weak_tls",
        title="Weak TLS configuration",
        target_ref="example.com:443",
        severity="medium",
        confidence="high",
        summary="Server accepts deprecated ciphers.",
        impact="Traffic may be downgraded.",
        reproduction_notes="Run tls_inspect.",
        next_action="Disable weak ciphers.",
    )
    repository.create(finding)

    loaded = repository.get(finding.public_id)
    assert loaded is not None
    assert loaded.status == FindingStatus.OPEN
    assert loaded.confidence == "high"

    loaded.status = FindingStatus.CONFIRMED
    loaded.next_action = "Rotate TLS policy."
    repository.update(loaded)
    updated = repository.get(finding.public_id)

    assert updated is not None
    assert updated.status == FindingStatus.CONFIRMED
    assert updated.next_action == "Rotate TLS policy."
