from agent.settings import Settings
from conftest import create_redteam_operation
from models.job import JobStatus
from models.planner import PlannerMemoryWritebackStatus
from app.planner_service import PlannerService


class FakePlannerModel:
    def invoke(self, _messages):
        return type(
            "Response",
            (),
            {
                "content": (
                    '{"summary":"Planner summary.","rationale":"Planner rationale.","proposals":['
                    '{"job_type":"http_probe","target_ref":"https://example.com","arguments":{"method":"GET"},'
                    '"summary":"Probe https://example.com.","rationale":"Recent evidence points here."}'
                    "]}"
                )
            },
        )()


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_planner_service(settings):
    planner_service = PlannerService.from_settings(settings)
    planner_service.runtime.model_factory = lambda _settings: FakePlannerModel()
    return planner_service


def seed_operation_state(planner_service: PlannerService):
    operation = create_redteam_operation(
        planner_service.settings,
        title="Surface recon",
        objective="Inspect scoped web surface",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
    )
    job = planner_service.job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    job.status = JobStatus.SUCCEEDED
    planner_service.job_service.save_job(job)
    planner_service.runtime.evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        evidence_type="http_response",
        target_ref="https://example.com",
        title="Homepage probe",
        summary="Captured homepage response.",
    )
    planner_service.runtime.finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="tls_hostname_mismatch",
        title="TLS mismatch",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Certificate hostname mismatch.",
    )
    return operation, job


def test_planner_service_create_plan_writes_back_memory_entries(tmp_path):
    settings = build_settings(tmp_path)
    planner_service = build_planner_service(settings)
    operation, job = seed_operation_state(planner_service)

    first = planner_service.create_plan(operation.public_id)
    second = planner_service.create_plan(operation.public_id)

    assert first.memory_writeback is not None
    assert first.memory_writeback.status == PlannerMemoryWritebackStatus.SUCCEEDED
    assert first.memory_writeback.created_count == 3
    assert first.memory_writeback.skipped_count == 0
    assert second.memory_writeback is not None
    assert second.memory_writeback.status == PlannerMemoryWritebackStatus.SUCCEEDED
    assert second.memory_writeback.created_count == 3
    entries = planner_service.memory_service.list_memory_entries(operation.public_id)
    assert len(entries) == 6
    assert sum(1 for entry in entries if entry.entry_type == "web") == 4
    assert sum(1 for entry in entries if entry.entry_type == "tls") == 2
    assert any(entry.source_job_id == job.id for entry in entries)


def test_planner_service_create_plan_preserves_plan_when_memory_writeback_fails(tmp_path):
    settings = build_settings(tmp_path)
    planner_service = build_planner_service(settings)
    operation, _job = seed_operation_state(planner_service)
    original_create = planner_service.memory_service.create_memory_entry
    call_count = {"value": 0}

    def flaky_create_memory_entry(**kwargs):
        call_count["value"] += 1
        if call_count["value"] == 2:
            raise RuntimeError("boom")
        return original_create(**kwargs)

    planner_service.memory_service.create_memory_entry = flaky_create_memory_entry

    bundle = planner_service.create_plan(operation.public_id)

    assert bundle.plan.public_id == "PLN0001"
    assert bundle.memory_writeback is not None
    assert bundle.memory_writeback.status == PlannerMemoryWritebackStatus.FAILED
    assert bundle.memory_writeback.created_count == 1
    assert bundle.memory_writeback.error_message == "boom"
    persisted = planner_service.get_plan_bundle(bundle.plan.public_id)
    assert persisted.plan.public_id == bundle.plan.public_id
    assert len(planner_service.memory_service.list_memory_entries(operation.public_id)) == 1
