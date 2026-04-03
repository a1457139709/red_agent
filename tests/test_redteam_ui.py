from cli.ui import CliPresenter
from models.job import Job, JobStatus
from models.operation import Operation, OperationStatus
from models.scope_policy import ScopePolicy



def test_presenter_renders_operation_and_job_views():
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
        status=JobStatus.PENDING,
        arguments={"method": "GET"},
        dependency_job_ids=["dep-1"],
        timeout_seconds=30,
    )

    presenter.show_help("operation")
    presenter.show_help("job")
    presenter.show_operation_detail(operation, policy)
    presenter.show_job_detail(job)

    merged = "\n\n".join(outputs)
    assert "Operation Commands" in merged
    assert "/job create <operation_id>" in merged
    assert "Operation ID:" in merged and "O0001" in merged
    assert "Allowed Ports:" in merged and "80, 443" in merged
    assert "Job ID:" in merged and "J0001" in merged
    assert "Arguments:" in merged and "method" in merged
