from pathlib import Path
import sqlite3

import pytest

from domain.jobs import Job, JobStatus
from domain.operations import Operation, OperationArtifacts, OperationStatus, ScopePolicy
from domain.common import utc_now_iso
from storage.redteam import RedTeamStorage
from storage.repositories import JobRepository, OperationRepository, ScopePolicyRepository


def build_storage(tmp_path) -> RedTeamStorage:
    return RedTeamStorage(tmp_path / ".red-code" / "agent-redteam.db")


def test_red_team_storage_bootstrap_creates_database_and_metadata(tmp_path):
    storage = build_storage(tmp_path)

    assert storage.db_path.exists()

    with storage.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM app_metadata").fetchall()
        }

    assert {
        "app_metadata",
        "operations",
        "scope_policies",
        "planner_runs",
        "jobs",
        "job_dependencies",
        "evidence",
        "findings",
        "memory_profiles",
        "memory_entries",
        "memory_snapshots",
        "workers",
        "worker_leases",
        "job_events",
    }.issubset(tables)
    assert metadata == {
        "schema_family": "red_code",
        "schema_version": "3",
        "runtime_family": "red_team",
    }


def test_red_team_storage_rejects_missing_metadata_table(tmp_path):
    db_path = tmp_path / ".red-code" / "agent-redteam.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE legacy_only (id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="incompatible runtime schema"):
        RedTeamStorage(db_path)


def test_red_team_storage_rejects_wrong_runtime_family(tmp_path):
    db_path = tmp_path / ".red-code" / "agent-redteam.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.executemany(
        "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
        [
            ("schema_family", "red_code"),
            ("schema_version", "3"),
            ("runtime_family", "wrong_runtime"),
        ],
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="runtime family"):
        RedTeamStorage(db_path)


def test_red_team_storage_rejects_wrong_schema_version(tmp_path):
    db_path = tmp_path / ".red-code" / "agent-redteam.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.executemany(
        "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
        [
            ("schema_family", "red_code"),
            ("schema_version", "999"),
            ("runtime_family", "red_team"),
        ],
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="schema version"):
        RedTeamStorage(db_path)


def test_operation_repository_assigns_public_ids_and_supports_lookup(tmp_path):
    storage = build_storage(tmp_path)
    repository = OperationRepository(storage)

    first = repository.create(
        Operation.create(
            title="Internet edge recon",
            objective="Map external attack surface",
            workspace=str(tmp_path),
        )
    )
    second = repository.create(
        Operation.create(
            title="Web enum",
            objective="Enumerate HTTP endpoints",
            workspace=str(tmp_path),
        )
    )

    assert first.public_id == "O0001"
    assert second.public_id == "O0002"
    assert repository.get(first.public_id).id == first.id
    assert repository.get(first.id).public_id == first.public_id


def test_operation_repository_lists_recent_and_updates_fields(tmp_path):
    storage = build_storage(tmp_path)
    repository = OperationRepository(storage)

    first = repository.create(
        Operation.create(title="First", objective="One", workspace=str(tmp_path))
    )
    second = repository.create(
        Operation.create(title="Second", objective="Two", workspace=str(tmp_path))
    )

    listed = repository.list()
    assert [operation.id for operation in listed] == [second.id, first.id]

    first.status = OperationStatus.RUNNING
    first.last_error_code = "partial_failure"
    first.last_error_message = "still running but captured an error"
    first.updated_at = utc_now_iso()
    repository.update(first)

    reloaded = repository.get(first.id)
    assert reloaded.status == OperationStatus.RUNNING
    assert reloaded.last_error_code == "partial_failure"
    assert reloaded.last_error_message == "still running but captured an error"


def test_operation_repository_deletes_cleanly(tmp_path):
    storage = build_storage(tmp_path)
    repository = OperationRepository(storage)
    operation = repository.create(
        Operation.create(title="Delete me", objective="Cleanup", workspace=str(tmp_path))
    )

    repository.delete(operation.id)

    assert repository.get(operation.id) is None


def test_scope_policy_repository_upserts_and_round_trips_json_fields(tmp_path):
    storage = build_storage(tmp_path)
    operations = OperationRepository(storage)
    policies = ScopePolicyRepository(storage)
    operation = operations.create(
        Operation.create(title="Scoped op", objective="Use policy", workspace=str(tmp_path))
    )

    created = policies.upsert(
        ScopePolicy.create(
            operation_id=operation.id,
            allowed_hostnames=["host-a.example"],
            allowed_ips=["10.0.0.10"],
            allowed_domains=["example.com"],
            allowed_cidrs=["10.0.0.0/24"],
            allowed_ports=[80, 443],
            allowed_protocols=["tcp", "https"],
            denied_targets=["10.0.0.13"],
            allowed_tool_categories=["recon", "http"],
            max_concurrency=4,
            requests_per_minute=120,
            packets_per_second=20,
            requires_confirmation_for=["high_rate_scan"],
        )
    )
    updated = policies.upsert(
        ScopePolicy(
            id="new-id-ignored-on-update",
            operation_id=operation.id,
            allowed_hostnames=["host-b.example"],
            allowed_ips=["10.0.0.11"],
            allowed_domains=["example.org"],
            allowed_cidrs=["192.168.1.0/24"],
            allowed_ports=[8080],
            allowed_protocols=["tcp"],
            denied_targets=["192.168.1.99"],
            allowed_tool_categories=["web"],
            max_concurrency=2,
            requests_per_minute=60,
            packets_per_second=10,
            requires_confirmation_for=["manual_validation"],
            created_at="ignored",
            updated_at=utc_now_iso(),
        )
    )

    loaded = policies.get_by_operation_id(operation.id)

    assert created.id == updated.id
    assert loaded.allowed_hostnames == ["host-b.example"]
    assert loaded.allowed_ips == ["10.0.0.11"]
    assert loaded.allowed_domains == ["example.org"]
    assert loaded.allowed_ports == [8080]
    assert loaded.allowed_tool_categories == ["web"]
    assert loaded.requires_confirmation_for == ["manual_validation"]


def test_job_repository_assigns_public_ids_lists_and_updates(tmp_path):
    storage = build_storage(tmp_path)
    operations = OperationRepository(storage)
    jobs = JobRepository(storage)
    operation = operations.create(
        Operation.create(title="Job op", objective="Create jobs", workspace=str(tmp_path))
    )

    first = jobs.create(
        Job.create(
            operation_id=operation.id,
            job_type="dns_lookup",
            tool_name="dns_lookup",
            target_ref="example.com",
            args={"record_types": ["A", "AAAA"]},
        )
    )
    second = jobs.create(
        Job.create(
            operation_id=operation.id,
            job_type="http_probe",
            tool_name="http_probe",
            target_ref="https://example.com",
            args={"path": "/"},
        )
    )

    assert first.public_id == "J0001"
    assert second.public_id == "J0002"
    assert jobs.get(first.public_id).id == first.id
    assert [job.id for job in jobs.list_by_operation(operation.id)] == [second.id, first.id]

    first.status = JobStatus.RUNNING
    first.started_at = utc_now_iso()
    first.updated_at = utc_now_iso()
    jobs.update(first)

    loaded = jobs.get(first.id)
    assert loaded.status == JobStatus.RUNNING
    assert loaded.started_at is not None
    assert loaded.args == {"record_types": ["A", "AAAA"]}


def test_operation_artifacts_manage_only_operation_scoped_paths(tmp_path):
    app_data_dir = tmp_path / ".red-code"
    managed = OperationArtifacts(app_data_dir=app_data_dir, operation_id="operation-123")
    sibling = app_data_dir / "operations" / "operation-other"
    sibling.mkdir(parents=True, exist_ok=True)
    (sibling / "keep.txt").write_text("keep", encoding="utf-8")

    managed.ensure()
    (managed.evidence_dir / "artifact.txt").write_text("artifact", encoding="utf-8")

    assert managed.operation_dir == app_data_dir / "operations" / "operation-123"
    assert managed.evidence_dir.exists()
    assert managed.planner_dir.exists()
    assert managed.exports_dir.exists()

    managed.delete()

    assert not managed.operation_dir.exists()
    assert sibling.exists()
    assert (sibling / "keep.txt").exists()
