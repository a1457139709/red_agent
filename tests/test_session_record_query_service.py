import inspect

from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.report_service import ReportService
from app.run_service import RunService
from app.session_event_service import SessionEventService
from app.session_record_query_service import SessionRecordQueryService
from app.session_service import SessionService
from models.job import JobLogLevel, JobStatus
from models.run import TaskLogLevel
from models.session import SessionMode, SessionStatus
from models.session_event import SessionEventLevel, SessionEventType


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def seed_session_records(settings):
    session_service = SessionService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    report_service = ReportService.from_settings(settings)
    query_service = SessionRecordQueryService.from_settings(settings)

    session = session_service.create_session(
        title="Retrieval Session",
        goal="Query session-owned records",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
    )
    run = run_service.start_run(session.public_id)
    run_service.write_log(
        session_identifier=session.public_id,
        run_id=run.id,
        level=TaskLogLevel.INFO,
        message="tool_completed",
        payload={"tool_name": "http_probe", "result_summary": "200 OK"},
    )
    run = run_service.complete_run(
        run.id,
        step_count=2,
        effective_skill_name="surface-recon",
        effective_tools=["http_probe"],
    )
    job = job_service.create_job(
        session_identifier=session.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        status=JobStatus.SUCCEEDED,
    )
    job_service.write_log(
        job_identifier=job.public_id,
        level=JobLogLevel.INFO,
        message="artifact_persisted",
        payload={"artifact_type": "http_response"},
    )
    event_service.create_event(
        session_identifier=session.public_id,
        job_identifier=job.public_id,
        event_type=SessionEventType.EXECUTION_SUCCEEDED,
        level=SessionEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Probe completed.",
        payload={"run_id": run.public_id},
    )
    artifact = artifact_service.create_artifact(
        session_identifier=session.public_id,
        source_job_identifier=job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response headers.",
        artifact_path="artifacts/http-response.json",
    )
    finding = finding_service.create_finding(
        session_identifier=session.public_id,
        source_job_identifier=job.public_id,
        finding_type="reachable_service",
        title="Reachable service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="The service responds successfully.",
    )
    finding_service.link_artifacts(finding.public_id, [artifact.public_id])
    report = report_service.create_report(
        session_identifier=session.public_id,
        report_type="session_summary",
        title="Session summary",
        summary="Summarize the session.",
        artifact_identifiers=[artifact.public_id],
        finding_identifiers=[finding.public_id],
        output_payload={"ok": True},
    )

    return {
        "query_service": query_service,
        "session": session,
        "run": run,
        "job": job,
        "artifact": artifact,
        "finding": finding,
        "report": report,
    }


def test_session_record_query_service_aggregates_history_and_execution_steps(tmp_path):
    settings = build_settings(tmp_path)
    seeded = seed_session_records(settings)
    query_service = seeded["query_service"]
    session = seeded["session"]
    artifact = seeded["artifact"]
    finding = seeded["finding"]
    report = seeded["report"]

    history = query_service.get_history_summary(session.public_id)
    execution_steps = query_service.list_execution_steps(session.public_id)

    assert history.layer_summary.runs == 1
    assert history.layer_summary.logs == 1
    assert history.layer_summary.jobs == 1
    assert history.layer_summary.events == 1
    assert history.layer_summary.artifacts == 1
    assert history.layer_summary.findings == 1
    assert history.layer_summary.reports == 1
    assert history.recent_artifacts[0].public_id == artifact.public_id
    assert history.recent_findings[0].public_id == finding.public_id
    assert history.recent_reports[0].public_id == report.public_id

    source_types = {step.source_type for step in execution_steps}
    assert {"run", "log", "job", "event"}.issubset(source_types)
    assert any(step.run_public_id == seeded["run"].public_id for step in execution_steps)
    assert any(step.job_public_id == seeded["job"].public_id for step in execution_steps)


def test_session_record_query_service_filters_records_by_session_and_public_id(tmp_path):
    settings = build_settings(tmp_path)
    seeded = seed_session_records(settings)
    query_service = seeded["query_service"]
    session = seeded["session"]
    artifact = seeded["artifact"]
    finding = seeded["finding"]
    report = seeded["report"]

    artifacts = query_service.list_artifacts(session.public_id, artifact_identifier=artifact.public_id)
    findings = query_service.list_findings(session.public_id, finding_identifier=finding.public_id)
    reports = query_service.list_reports(session.public_id, report_identifier=report.public_id)

    assert [item.public_id for item in artifacts] == [artifact.public_id]
    assert [item.public_id for item in findings] == [finding.public_id]
    assert [item.public_id for item in reports] == [report.public_id]


def test_session_record_query_service_explains_finding_with_traceable_records(tmp_path):
    settings = build_settings(tmp_path)
    seeded = seed_session_records(settings)
    query_service = seeded["query_service"]
    session = seeded["session"]
    artifact = seeded["artifact"]
    finding = seeded["finding"]
    job = seeded["job"]
    run = seeded["run"]

    explanation = query_service.explain_finding(session.public_id, finding.public_id)

    assert explanation.finding.public_id == finding.public_id
    assert [item.public_id for item in explanation.linked_artifacts] == [artifact.public_id]
    assert explanation.source_job is not None
    assert explanation.source_job.public_id == job.public_id
    assert explanation.related_events
    assert run.public_id in explanation.related_run_ids
    assert explanation.missing_segments == []
    assert explanation.is_complete


def test_session_record_query_service_marks_incomplete_traces_explicitly(tmp_path):
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    query_service = SessionRecordQueryService.from_settings(settings)

    session = session_service.create_session(
        title="Incomplete Trace",
        goal="Show missing evidence",
        mode=SessionMode.REDTEAM,
        status=SessionStatus.ACTIVE,
    )
    finding = finding_service.create_finding(
        session_identifier=session.public_id,
        finding_type="configuration_issue",
        title="Configuration issue",
        target_ref="example.com",
        severity="low",
        confidence="medium",
        summary="Sparse trace data.",
    )

    explanation = query_service.explain_finding(session.public_id, finding.public_id)

    assert explanation.finding.public_id == finding.public_id
    assert explanation.linked_artifacts == []
    assert explanation.source_job is None
    assert explanation.related_events == []
    assert explanation.related_run_ids == []
    assert explanation.missing_segments == [
        "linked_artifacts",
        "source_job",
        "execution_events",
        "source_run",
    ]
    assert not explanation.is_complete


def test_session_record_query_service_has_no_primary_legacy_service_dependency():
    source = inspect.getsource(SessionRecordQueryService)

    assert "TaskService" not in source
    assert "OperationService" not in source
    assert "task_service" not in source
    assert "operation_service" not in source
