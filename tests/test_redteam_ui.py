from app.dashboard_service import OperationDashboard
from cli.ui import CliPresenter
from models.evidence import Evidence
from models.finding import Finding
from models.job import Job, JobStatus
from models.operation import Operation, OperationStatus
from models.operation_event import OperationEvent, OperationEventLevel, OperationEventType
from models.scope_policy import ScopePolicy


def test_presenter_renders_operation_job_finding_evidence_and_dashboard_views():
    outputs = []
    presenter = CliPresenter.for_callbacks(text_output=outputs.append)
    operation = Operation(
        id="op-uuid",
        public_id="O0001",
        title="Web recon",
        objective="Inspect attack surface",
        workspace="D:/workspace",
        scope_policy_id="scope-1",
        status=OperationStatus.DRAFT,
    )
    policy = ScopePolicy(
        id="scope-1",
        operation_id=operation.id,
        allowed_hosts=["example.com"],
        allowed_domains=["example.com"],
        allowed_cidrs=["10.0.0.0/24"],
        allowed_ports=[80, 443],
        allowed_protocols=["http", "https"],
        denied_targets=["admin.example.com"],
        allowed_tool_categories=["recon"],
        confirmation_required_actions=["port_scan"],
    )
    job = Job(
        id="job-uuid",
        public_id="J0001",
        operation_id=operation.id,
        job_type="http_probe",
        target_ref="https://example.com",
        status=JobStatus.TIMED_OUT,
        arguments={"method": "GET"},
        dependency_job_ids=["dep-1"],
        timeout_seconds=30,
        cancel_requested_at="2026-04-07T00:01:00+00:00",
        cancel_reason="operator stop",
    )
    finding = Finding.create(
        operation_id=operation.id,
        source_job_id=job.id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
    )
    finding.public_id = "F0001"
    evidence = Evidence.create(
        operation_id=operation.id,
        job_id=job.id,
        evidence_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response.",
    )
    evidence.public_id = "E0001"
    event = OperationEvent.create(
        operation_id=operation.id,
        job_id=job.id,
        event_type=OperationEventType.EXECUTION_FAILED,
        level=OperationEventLevel.ERROR,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Probe failed.",
    )
    dashboard = OperationDashboard(
        operation=operation,
        policy=policy,
        job_counts={"timed_out": 1},
        flagged_jobs=[job],
        finding_counts={"open": 1},
        recent_findings=[finding],
        evidence_count=1,
        recent_evidence=[evidence],
        event_counts={
            "admission_denied": 0,
            "confirmation_denied": 0,
            "execution_failed": 1,
        },
        recent_events=[event],
    )

    presenter.show_help("operation")
    presenter.show_help("job")
    presenter.show_help("finding")
    presenter.show_help("evidence")
    presenter.show_help("dashboard")
    presenter.show_operation_detail(operation, policy)
    presenter.show_job_detail(job)
    presenter.show_finding_detail(finding, linked_evidence_ids=[evidence.public_id])
    presenter.show_evidence_detail(evidence, linked_finding_ids=[finding.public_id])
    presenter.show_dashboard(dashboard)

    merged = "\n\n".join(outputs)
    assert "Operation Commands" in merged
    assert "/job cancel <job_id>" in merged
    assert "/finding show <finding_id>" in merged
    assert "/evidence show <evidence_id>" in merged
    assert "/dashboard <operation_id>" in merged
    assert "Operation ID:" in merged and "O0001" in merged
    assert "Allowed Ports:" in merged and "80, 443" in merged
    assert "Job ID:" in merged and "J0001" in merged
    assert "Cancel Requested At:" in merged
    assert "Finding ID:" in merged and "F0001" in merged
    assert "Linked Evidence IDs:" in merged and "E0001" in merged
    assert "Evidence ID:" in merged and "E0001" in merged
    assert "Linked Finding IDs:" in merged and "F0001" in merged
    assert "Dashboard Summary" in merged
    assert "Recent Failed / Timed-Out / Blocked Jobs" in merged
