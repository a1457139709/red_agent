import json

from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from app.security_tool_execution_service import SecurityToolExecutionService
from reporting.evidence_export import EvidenceExportService
from models.operation import OperationStatus
from tools.contracts import EvidenceCandidate, FindingCandidate, SecurityToolResult


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_generate_operation_export_writes_json_summaries_with_traceability(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)
    export_service = EvidenceExportService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Export",
        objective="Generate structured output",
        allowed_domains=["example.com"],
        allowed_protocols=["tls"],
        allowed_ports=[443],
        allowed_tool_categories=["recon"],
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="tls_inspect",
        target_ref="example.com:443",
    )

    monkeypatch.setattr(
        execution_service.security_tool_executor,
        "execute",
        lambda tool_name, *, invocation, target: SecurityToolResult(
            tool_name=tool_name,
            target=target.normalized_target,
            summary="TLS inspection summary",
            payload={"tls_version": "TLSv1.3"},
            evidence_candidates=[
                EvidenceCandidate(
                    evidence_type="tls_certificate",
                    target_ref=target.normalized_target,
                    title="TLS inspection",
                    summary="Captured certificate details.",
                    content_type="application/json",
                    payload={"tls_version": "TLSv1.3"},
                )
            ],
            finding_candidates=[
                FindingCandidate(
                    finding_type="tls_hostname_mismatch",
                    title="TLS certificate hostname mismatch",
                    target_ref=target.normalized_target,
                    severity="medium",
                    confidence="high",
                    summary="Hostname mismatch observed.",
                    impact="Clients may reject the certificate.",
                    reproduction_notes="Run tls_inspect against the endpoint.",
                    next_action="Confirm SAN coverage.",
                )
            ],
        ),
    )

    result = execution_service.execute_job(job_identifier=job.public_id)
    export = export_service.generate_operation_export(operation.public_id, export_name="phase5-export")

    assert result.status == "succeeded"
    assert len(export.files) == 3
    for path in export.files:
        assert path.exists()

    summary = json.loads((export.export_dir / "operation-summary.json").read_text(encoding="utf-8"))
    findings = json.loads((export.export_dir / "findings.json").read_text(encoding="utf-8"))
    evidence = json.loads((export.export_dir / "evidence-index.json").read_text(encoding="utf-8"))

    assert summary["counts"]["findings"] == 1
    assert findings[0]["evidence_public_ids"]
    assert evidence[0]["finding_public_ids"]
