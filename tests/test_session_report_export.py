import inspect
import json

import app.security_tool_execution_service as security_tool_execution_module
import reporting
from agent.settings import Settings
from app.job_service import JobService
from app.security_tool_execution_service import SecurityToolExecutionService
from app.session_service import SessionService
from conftest import create_redteam_operation
from models.operation import OperationStatus
from reporting import SessionExportResult, SessionReportExportService
from tools.contracts import EvidenceCandidate, FindingCandidate, SecurityToolResult


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_generate_session_export_writes_json_summaries_with_traceability(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    execution_service = SecurityToolExecutionService.from_settings(settings)
    export_service = SessionReportExportService.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Export",
        objective="Generate structured output",
        allowed_domains=["example.com"],
        allowed_protocols=["tls"],
        allowed_ports=[443],
        allowed_tool_categories=["recon"],
        status=OperationStatus.READY,
    )
    session = session_service.require_session(operation.id)
    job = job_service.create_job(
        session_identifier=session.public_id,
        job_type="tls_inspect",
        target_ref="example.com:443",
    )

    monkeypatch.setattr(
        security_tool_execution_module,
        "execute_security_tool_in_subprocess",
        lambda **kwargs: SecurityToolResult(
            tool_name=kwargs["tool_name"],
            target=kwargs["target"].normalized_target,
            summary="TLS inspection summary",
            payload={"tls_version": "TLSv1.3"},
            evidence_candidates=[
                EvidenceCandidate(
                    evidence_type="tls_certificate",
                    target_ref=kwargs["target"].normalized_target,
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
                    target_ref=kwargs["target"].normalized_target,
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
    export = export_service.generate_session_export(session.public_id, export_name="phase7-export")

    assert result.status == "succeeded"
    assert isinstance(export, SessionExportResult)
    assert len(export.files) == 3
    assert export.session_id == session.id
    assert export.session_public_id == session.public_id

    for path in export.files:
        assert path.exists()
        assert ".red-code" in str(path)
        assert "sessions" in str(path)
        assert session.id in str(path)
        assert "reports" in str(path)

    payloads_by_name = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in export.files
    }
    summary = next(payload for name, payload in payloads_by_name.items() if "session_summary" in name)
    findings = next(payload for name, payload in payloads_by_name.items() if "findings" in name)
    artifacts = next(payload for name, payload in payloads_by_name.items() if "artifact_index" in name)

    assert "session" in summary
    assert "scope_policy" in summary
    assert "operation" not in summary
    assert "evidence" not in summary["counts"]
    assert summary["counts"]["findings"] == 1
    assert summary["counts"]["artifacts"] == 1
    assert "operation_id" not in findings[0]
    assert "evidence_public_ids" not in findings[0]
    assert findings[0]["artifact_public_ids"]
    assert "operation_id" not in artifacts[0]
    assert "evidence_type" not in artifacts[0]
    assert artifacts[0]["finding_public_ids"]


def test_session_report_export_public_api_is_session_first():
    signature = inspect.signature(SessionReportExportService.generate_session_export)
    source = inspect.getsource(SessionReportExportService)

    assert "session_identifier" in signature.parameters
    assert "operation_identifier" not in signature.parameters
    assert "EvidenceExportService" not in source
    assert "SessionReportExportService" in reporting.__all__
    assert "SessionExportResult" in reporting.__all__
    assert "EvidenceExportService" not in reporting.__all__
    assert "OperationExportResult" not in reporting.__all__
