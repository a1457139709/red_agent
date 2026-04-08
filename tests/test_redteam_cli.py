from agent.settings import Settings
from app.dashboard_service import DashboardService
from app.evidence_service import EvidenceService
from app.finding_service import FindingService
from app.job_service import JobService
from app.memory_service import MemoryService
from app.operation_service import OperationService
from app.planner_service import PlannerService
from models.planner import PlannerPlanStatus, PlannerProposalKind
from orchestration.planner_runtime import PlannerRuntime
from storage.repositories.planner import PlannerRepository
from storage.sqlite import SQLiteStorage
from models.job import JobStatus
from models.operation import OperationStatus
from main import (
    handle_dashboard_command,
    handle_evidence_command,
    handle_finding_command,
    handle_job_command,
    handle_operation_command,
    handle_planner_command,
)


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


class FakePlannerModel:
    def invoke(self, _messages):
        content = (
            '{"summary":"Planner summary.","rationale":"Planner rationale.","proposals":['
            '{"job_type":"http_probe","target_ref":"https://example.com","arguments":{"method":"GET"},'
            '"summary":"Probe https://example.com.","rationale":"Recent evidence points here."},'
            '{"job_type":"http_probe","target_ref":"https://admin.example.net","arguments":{"method":"GET"},'
            '"summary":"Blocked probe.","rationale":"Out of scope."}'
            "]}"
        )
        return type(
            "Response",
            (),
            {"content": content},
        )()


def build_planner_service(settings):
    storage = SQLiteStorage(settings.sqlite_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    runtime = PlannerRuntime(
        operation_service=operation_service,
        job_service=job_service,
        evidence_service=EvidenceService.from_settings(settings),
        finding_service=FindingService.from_settings(settings),
        memory_service=MemoryService.from_settings(settings),
        settings=settings,
        model_factory=lambda _settings: FakePlannerModel(),
    )
    return PlannerService(
        repository=PlannerRepository(storage),
        runtime=runtime,
        operation_service=operation_service,
        job_service=job_service,
        settings=settings,
    )


def test_operation_commands_create_list_show_pause_and_resume(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    planner_service = PlannerService.from_settings(settings)
    outputs = []
    errors = []
    infos = []
    successes = []
    responses = iter([
        "Surface recon",
        "Inspect public web surface",
        "example.com",
        "example.com",
        "10.0.0.0/24",
        "80,443",
        "http,https",
        "admin.example.com",
        "recon,http",
        "2",
        "60",
        "port_scan",
    ])

    def fake_input(_prompt):
        return next(responses)

    assert handle_operation_command(
        "/operation create",
        operation_service=operation_service,
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    operation = operation_service.list_operations(limit=1)[0]

    assert handle_operation_command(
        "/operation list",
        operation_service=operation_service,
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_operation_command(
        f"/operation show {operation.public_id}",
        operation_service=operation_service,
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_operation_command(
        f"/operation resume {operation.public_id}",
        operation_service=operation_service,
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_operation_command(
        f"/operation pause {operation.public_id}",
        operation_service=operation_service,
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any(f"Created operation {operation.public_id}" in message for message in successes)
    assert any(operation.public_id in message and "Surface recon" in message for message in outputs)
    assert any("Scope Policy" in message and "Allowed Ports:" in message for message in outputs)
    assert any("Operation Context Summary" in message for message in outputs)
    assert any("/planner plan" in message for message in infos)
    assert any(f"Resumed operation {operation.public_id}" in message for message in successes)
    assert any(f"Paused operation {operation.public_id}" in message for message in successes)
    assert operation_service.require_operation(operation.public_id).status == OperationStatus.PAUSED
    assert not errors


def test_job_commands_create_list_show_cancel_and_review_views(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    evidence_service = EvidenceService.from_settings(settings)
    dashboard_service = DashboardService.from_settings(settings)
    outputs = []
    errors = []
    successes = []

    operation = operation_service.create_operation(title="Probe", objective="Inspect target")
    responses = iter([
        "http_probe",
        "https://example.com",
        '{"method": "GET"}',
        "",
        "30",
        "1",
    ])

    def fake_input(_prompt):
        return next(responses)

    assert handle_job_command(
        f"/job create {operation.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    job = job_service.list_jobs(operation.public_id, limit=1)[0]
    evidence = evidence_service.create_evidence(
        operation_identifier=operation.public_id,
        job_identifier=job.public_id,
        evidence_type="http_response",
        target_ref=job.target_ref,
        title="HTTP response",
        summary="Captured response",
    )
    finding = finding_service.create_finding(
        operation_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref=job.target_ref,
        severity="medium",
        confidence="high",
        summary="Service exposed",
    )
    finding_service.link_evidence(finding.public_id, [evidence.public_id])

    assert handle_job_command(
        f"/job list {operation.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_job_command(
        f"/job show {job.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_job_command(
        f"/job cancel {job.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=lambda _prompt: "operator stop",
    )
    assert handle_finding_command(
        f"/finding list {operation.public_id}",
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_finding_command(
        f"/finding show {finding.public_id}",
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_finding_command(
        f"/finding confirm {finding.public_id}",
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_evidence_command(
        f"/evidence show {evidence.public_id}",
        evidence_service=evidence_service,
        finding_service=finding_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_dashboard_command(
        f"/dashboard {operation.public_id}",
        dashboard_service=dashboard_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any(f"Created job {job.public_id}" in message for message in successes)
    assert any(job.public_id in message and "http_probe" in message for message in outputs)
    assert any("Arguments:" in message and "method" in message for message in outputs)
    assert any(f"Requested cancellation for job {job.public_id}" in message for message in successes)
    assert any(finding.public_id in message and "Exposed service" in message for message in outputs)
    assert any("Linked Evidence IDs:" in message and evidence.public_id in message for message in outputs)
    assert any("Linked Finding IDs:" in message and finding.public_id in message for message in outputs)
    assert any("Dashboard Summary" in message and operation.public_id in message for message in outputs)
    assert not errors


def test_planner_commands_plan_and_apply(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    planner_service = build_planner_service(settings)
    outputs = []
    infos = []
    errors = []
    successes = []

    operation = operation_service.create_operation(
        title="Plan",
        objective="Inspect target",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
    )

    assert handle_planner_command(
        f"/planner plan {operation.public_id}",
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    bundle = planner_service.get_plan_bundle("PLN0001")
    proposed = [proposal for proposal in bundle.proposals if proposal.proposal_kind == PlannerProposalKind.PROPOSED]
    assert proposed

    assert handle_planner_command(
        f"/planner apply {bundle.plan.public_id} 1",
        planner_service=planner_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    jobs = job_service.list_jobs(operation.public_id)
    assert len(jobs) == 1
    assert jobs[0].job_type == "http_probe"
    assert any("Planner Plan" in message and bundle.plan.public_id in message for message in outputs)
    assert any("Planner Proposals" in message for message in outputs)
    assert any("Skipped / Blocked Proposals" in message for message in outputs)
    assert any(f"Applied 1 planner proposal(s) from {bundle.plan.public_id}" in message for message in successes)
    assert not errors


def test_planner_apply_is_idempotent_for_already_applied_proposals(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    planner_service = build_planner_service(settings)

    operation = operation_service.create_operation(
        title="Plan",
        objective="Inspect target",
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
    )
    bundle = planner_service.create_plan(operation.public_id)

    first = planner_service.apply_plan(bundle.plan.public_id, selected_indices=[1])
    second = planner_service.apply_plan(bundle.plan.public_id, selected_indices=[1])

    assert first.plan.status == PlannerPlanStatus.APPLIED
    assert second.plan.status == PlannerPlanStatus.APPLIED
    assert len(second.applied_jobs) == 0
    assert len(second.skipped_proposals) == 1
    refreshed = planner_service.get_plan_bundle(bundle.plan.public_id)
    assert refreshed.plan.status == PlannerPlanStatus.APPLIED


def test_job_cancel_reports_noop_for_terminal_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    outputs = []
    infos = []
    errors = []
    successes = []

    operation = operation_service.create_operation(title="Probe", objective="Inspect target")
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    job.status = JobStatus.SUCCEEDED
    job_service.save_job(job)

    assert handle_job_command(
        f"/job cancel {job.public_id}",
        job_service=job_service,
        operation_service=operation_service,
        text_output=outputs.append,
        info_output=infos.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=lambda _prompt: "",
    )

    assert not successes
    assert any("already terminal" in message and "succeeded" in message for message in infos)
    assert not errors
