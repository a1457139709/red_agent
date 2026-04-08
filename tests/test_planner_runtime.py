from types import SimpleNamespace
import json

from agent.settings import Settings
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.memory_service import MemoryService
from app.operation_service import OperationService
from models.finding import FindingStatus
from models.job import JobStatus
from models.planner import PlannerProposalKind, PlannerSource
from orchestration.planner_runtime import PlannerRuntime


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


class FakeModel:
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, _messages):
        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


def build_runtime(tmp_path, *, model_factory):
    settings = build_settings(tmp_path)
    return (
        settings,
        PlannerRuntime(
            operation_service=OperationService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            evidence_service=EvidenceService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            memory_service=MemoryService.from_settings(settings),
            settings=settings,
            model_factory=model_factory,
        ),
    )


def seed_operation_state(runtime: PlannerRuntime):
    operation = runtime.operation_service.create_operation(
        title="Surface recon",
        objective="Inspect scoped web surface",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
    )
    job = runtime.job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    job.status = JobStatus.SUCCEEDED
    runtime.job_service.save_job(job)
    runtime.evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        evidence_type="http_response",
        target_ref="https://example.com",
        title="Homepage probe",
        summary="Captured homepage response.",
    )
    finding = runtime.finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="tls_hostname_mismatch",
        title="TLS mismatch",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Certificate hostname mismatch.",
    )
    assert finding.status == FindingStatus.OPEN
    runtime.memory_service.create_memory_entry(
        operation_identifier=operation.public_id,
        entry_type="web",
        key="target",
        value={"host": "example.com"},
        summary="Example host exposes a web surface.",
        source_job_identifier=job.public_id,
    )
    return operation


def test_planner_runtime_uses_model_and_marks_invalid_items(tmp_path):
    payload = {
        "summary": "Model summary.",
        "rationale": "Model rationale.",
        "proposals": [
            {
                "job_type": "http_probe",
                "target_ref": "https://example.com",
                "arguments": {"method": "GET"},
                "summary": "Probe in-scope target.",
                "rationale": "Recent evidence points here.",
            },
            {
                "job_type": "http_probe",
                "target_ref": "https://outside.example.net",
                "arguments": {"method": "GET"},
                "summary": "Probe out-of-scope target.",
                "rationale": "Should be blocked.",
            },
            {
                "job_type": "http_probe",
                "target_ref": "https://example.com",
                "arguments": {"method": "GET"},
                "summary": "Duplicate probe.",
                "rationale": "Duplicate.",
            },
        ],
    }
    settings, runtime = build_runtime(tmp_path, model_factory=lambda _settings: FakeModel(payload))
    del settings
    operation = seed_operation_state(runtime)

    result = runtime.create_plan(operation.public_id)

    assert result.planner_source == PlannerSource.MODEL
    assert any(proposal.proposal_kind == PlannerProposalKind.PROPOSED for proposal in result.proposals)
    assert any(proposal.proposal_kind == PlannerProposalKind.BLOCKED for proposal in result.proposals)
    assert any(
        proposal.proposal_kind == PlannerProposalKind.SKIPPED and "Duplicate proposal" in (proposal.skip_reason or "")
        for proposal in result.proposals
    )


def test_planner_runtime_falls_back_when_model_fails(tmp_path):
    settings, runtime = build_runtime(tmp_path, model_factory=lambda _settings: (_ for _ in ()).throw(RuntimeError("boom")))
    del settings
    operation = seed_operation_state(runtime)

    result = runtime.create_plan(operation.public_id)

    assert result.planner_source == PlannerSource.FALLBACK
    assert "Inspect scoped web surface" in result.summary
    assert any(proposal.proposal_kind == PlannerProposalKind.PROPOSED for proposal in result.proposals)


def test_planner_runtime_builds_operation_context_summary(tmp_path):
    settings, runtime = build_runtime(tmp_path, model_factory=lambda _settings: FakeModel({"summary": "", "rationale": "", "proposals": []}))
    del settings
    operation = seed_operation_state(runtime)

    summary = runtime.build_operation_context_summary(operation.public_id)

    assert operation.public_id in summary.operation_id
    assert "Scope allows" in summary.scope_summary
    assert "open finding" in summary.findings_summary
    assert "memory fact" in summary.memory_summary
    assert "Run /planner plan" not in summary.next_step_hint
