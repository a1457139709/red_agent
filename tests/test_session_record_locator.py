from agent.settings import Settings
from agent.state import SessionState
from app.artifact_service import ArtifactService
from app.checkpoint_service import CheckpointService
from app.finding_service import FindingService
from app.job_service import JobService
from app.memory_service import MemoryService
from app.report_service import ReportService
from app.run_service import RunService
from app.session_event_service import SessionEventService
from app.session_record_locator import SessionRecordLocator
from conftest import create_redteam_operation
from models.job import JobLogLevel
from models.run import SessionLogLevel
from models.session import SessionStatus
from models.session_event import SessionEventLevel, SessionEventType


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_session_record_locator_aggregates_session_layers(tmp_path):
    settings = build_settings(tmp_path)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    event_service = SessionEventService.from_settings(settings)
    memory_service = MemoryService.from_settings(settings)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    report_service = ReportService.from_settings(settings)
    locator = SessionRecordLocator.from_settings(settings)

    operation = create_redteam_operation(
        settings,
        title="Locator",
        objective="Aggregate session records",
        allowed_hosts=["example.com"],
        allowed_protocols=["https"],
        allowed_ports=[443],
        status=SessionStatus.ACTIVE,
    )
    run = run_service.start_run(operation.public_id)
    run_service.write_log(
        session_identifier=operation.public_id,
        run_id=run.id,
        level=SessionLogLevel.INFO,
        message="run_started",
    )
    checkpoint_service.save_checkpoint(
        session_identifier=operation.public_id,
        run_id=run.id,
        session_state=SessionState(),
    )
    job = job_service.create_job(
        session_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    job_service.write_log(
        job_identifier=job.public_id,
        level=JobLogLevel.INFO,
        message="queued",
    )
    event_service.create_event(
        session_identifier=operation.public_id,
        job_identifier=job.public_id,
        event_type=SessionEventType.EXECUTION_STARTED,
        level=SessionEventLevel.INFO,
        tool_name="http_probe",
        tool_category="recon",
        target_ref="https://example.com",
        message="Started.",
    )
    memory_service.create_memory_entry(
        session_identifier=operation.public_id,
        entry_type="web",
        key="example.com",
        value={"url": "https://example.com"},
        summary="Remember the web target.",
        source_job_identifier=job.public_id,
    )
    artifact = artifact_service.create_artifact(
        session_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response.",
        artifact_path="artifacts/http_response.json",
    )
    finding = finding_service.create_finding(
        session_identifier=operation.public_id,
        source_job_identifier=job.public_id,
        finding_type="exposed_service",
        title="Exposed service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Service is reachable.",
    )
    finding_service.link_artifacts(finding.public_id, [artifact.public_id])
    report_service.create_report(
        session_identifier=operation.public_id,
        report_type="artifact_index",
        title="Artifact index",
        summary="Summarize artifacts.",
        artifact_identifiers=[artifact.public_id],
        finding_identifiers=[finding.public_id],
        output_payload={"ok": True},
    )

    summary = locator.get_layer_summary(operation.public_id)

    assert summary.runs == 1
    assert summary.logs == 1
    assert summary.checkpoints == 1
    assert summary.jobs == 1
    assert summary.events == 1
    assert summary.memory_entries == 1
    assert summary.artifacts == 1
    assert summary.findings == 1
    assert summary.reports == 1


def test_session_record_locator_summary_uses_count_queries_without_list_truncation(tmp_path):
    settings = build_settings(tmp_path)
    locator = SessionRecordLocator.from_settings(settings)

    class StubRunService:
        def count_runs(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 20001

        def count_logs(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 30002

        def list_runs(self, session_identifier: str, *, limit=20):
            raise AssertionError("summary should not enumerate runs")

        def list_logs(self, session_identifier: str, *, limit=20):
            raise AssertionError("summary should not enumerate logs")

    class StubCheckpointService:
        def count_checkpoints(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 40003

        def list_checkpoints(self, session_identifier: str, *, limit=20):
            raise AssertionError("summary should not enumerate checkpoints")

    class StubJobService:
        def count_jobs(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 5

    class StubSessionEventService:
        def count_events(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 6

    class StubMemoryService:
        def count_memory_entries(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 7

    class StubArtifactService:
        def count_artifacts(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 8

    class StubFindingService:
        def count_findings(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 9

    class StubReportService:
        def count_reports(self, session_identifier: str) -> int:
            assert session_identifier == "S0001"
            return 10

    locator.run_service = StubRunService()
    locator.checkpoint_service = StubCheckpointService()
    locator.job_service = StubJobService()
    locator.session_event_service = StubSessionEventService()
    locator.memory_service = StubMemoryService()
    locator.artifact_service = StubArtifactService()
    locator.finding_service = StubFindingService()
    locator.report_service = StubReportService()

    summary = locator.get_layer_summary("S0001")

    assert summary.runs == 20001
    assert summary.logs == 30002
    assert summary.checkpoints == 40003
    assert summary.jobs == 5
    assert summary.events == 6
    assert summary.memory_entries == 7
    assert summary.artifacts == 8
    assert summary.findings == 9
    assert summary.reports == 10
