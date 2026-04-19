from types import SimpleNamespace
import json

from agent.settings import Settings
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.memory_service import MemoryService
from app.operation_service import OperationService
from app.scope_policy_service import ScopePolicyService
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
            scope_policy_service=ScopePolicyService.from_settings(settings),
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


def test_planner_runtime_derives_memory_candidates_from_structured_state(tmp_path):
    settings, runtime = build_runtime(tmp_path, model_factory=lambda _settings: FakeModel({"summary": "ignore", "rationale": "ignore", "proposals": []}))
    del settings
    operation = runtime.operation_service.create_operation(
        title="Memory",
        objective="Derive memory",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
    )
    http_job = runtime.job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    http_job.status = JobStatus.SUCCEEDED
    runtime.job_service.save_job(http_job)
    tls_job = runtime.job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="tls_inspect",
        target_ref="example.com:443",
    )
    tls_job.status = JobStatus.SUCCEEDED
    runtime.job_service.save_job(tls_job)
    port_job = runtime.job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="port_scan",
        target_ref="example.com",
    )
    port_job.status = JobStatus.SUCCEEDED
    runtime.job_service.save_job(port_job)
    runtime.evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=http_job.public_id,
        evidence_type="http_response",
        target_ref="https://example.com",
        title="Homepage probe",
        summary="Homepage.",
    )
    runtime.evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=port_job.public_id,
        evidence_type="dns_response",
        target_ref="example.com",
        title="DNS response",
        summary="DNS.",
    )
    runtime.evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=tls_job.public_id,
        evidence_type="tls_certificate",
        target_ref="example.com:443",
        title="TLS certificate",
        summary="TLS.",
    )
    runtime.finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=tls_job.public_id,
        finding_type="tls_hostname_mismatch",
        title="TLS mismatch",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Mismatch.",
    )

    result = runtime.derive_memory_candidates(operation.public_id)

    assert result.skipped_count == 0
    web_candidates = [candidate for candidate in result.candidates if candidate.entry_type == "web"]
    tls_candidates = [candidate for candidate in result.candidates if candidate.entry_type == "tls"]
    host_candidates = [candidate for candidate in result.candidates if candidate.entry_type == "host"]
    assert any(candidate.key == "example.com" and candidate.value["source_type"] == "web" for candidate in web_candidates)
    assert any(candidate.key == "example.com:443" and candidate.value["source_type"] == "tls" for candidate in tls_candidates)
    assert any(candidate.key == "example.com" and candidate.value["source_type"] == "host" for candidate in host_candidates)
    assert any(candidate.summary == "Planner recorded example.com as a stable web target." for candidate in web_candidates)
    assert any(candidate.summary == "Planner recorded example.com as a stable TLS-relevant target." for candidate in tls_candidates)
    assert any(candidate.summary == "Planner recorded example.com as a stable host target." for candidate in host_candidates)
    assert any(candidate.source_job_identifier == http_job.id for candidate in web_candidates)
    assert any(candidate.source_job_identifier == tls_job.id for candidate in tls_candidates)


def test_planner_runtime_memory_derivation_deduplicates_identical_candidates(tmp_path):
    settings, runtime = build_runtime(tmp_path, model_factory=lambda _settings: FakeModel({"summary": "", "rationale": "", "proposals": []}))
    del settings
    operation = seed_operation_state(runtime)
    context = runtime.build_context(operation.public_id)
    duplicated_context = context.__class__(
        operation=context.operation,
        policy=context.policy,
        successful_jobs=[context.successful_jobs[0], context.successful_jobs[0]],
        evidence_items=[context.evidence_items[0], context.evidence_items[0]],
        open_findings=[context.open_findings[0], context.open_findings[0]],
        memory_entries=context.memory_entries,
        context_hash=context.context_hash,
    )

    result = runtime.derive_memory_candidates_from_context(duplicated_context)

    assert len(result.candidates) == 3
    assert result.skipped_count == 3
