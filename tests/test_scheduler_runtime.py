from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time

from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from app.scoped_execution_service import ScopedExecutionResult
from models.job import JobStatus
from models.operation import OperationStatus
from models.run import utc_now_iso
from orchestration.job_service import JobOrchestrationService
from orchestration.scheduler import Scheduler
from runtime.worker import WorkerRuntime


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = b"runtime ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A003
        return


def run_http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_job_runtime_fields_round_trip_and_atomic_claim(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    orchestration = JobOrchestrationService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Lease jobs safely",
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    job.status = JobStatus.QUEUED
    job.queued_at = "2026-04-07T00:00:00+00:00"
    job.lease_owner = "worker-seed"
    job.lease_token = "lease-seed"
    job.lease_expires_at = "2026-04-07T00:00:15+00:00"
    job.last_heartbeat_at = "2026-04-07T00:00:05+00:00"
    job.cancel_requested_at = "2026-04-07T00:00:06+00:00"
    job.cancel_reason = "stop"
    job.retry_after = "2026-04-07T00:00:20+00:00"
    job.updated_at = "2026-04-07T00:00:06+00:00"
    job_service.save_job(job)

    loaded = job_service.require_job(job.public_id)
    assert loaded.lease_owner == "worker-seed"
    assert loaded.lease_token == "lease-seed"
    assert loaded.last_heartbeat_at == "2026-04-07T00:00:05+00:00"
    assert loaded.cancel_reason == "stop"
    assert loaded.retry_after == "2026-04-07T00:00:20+00:00"

    loaded.lease_owner = None
    loaded.lease_token = None
    loaded.lease_expires_at = None
    loaded.last_heartbeat_at = None
    loaded.cancel_requested_at = None
    loaded.cancel_reason = None
    loaded.retry_after = None
    loaded.updated_at = utc_now_iso()
    job_service.save_job(loaded)

    def claim(worker_id: str):
        return orchestration.claim_next_queued_job(
            worker_id=worker_id,
            now="2026-04-07T00:00:30+00:00",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(claim, "worker-a")
        second = executor.submit(claim, "worker-b")
        results = [first.result(), second.result()]

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0].status == JobStatus.RUNNING
    assert claimed[0].lease_owner in {"worker-a", "worker-b"}


def test_scheduler_queues_ready_jobs_and_blocks_failed_dependencies(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    scheduler = Scheduler.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Queue dependency graph",
        status=OperationStatus.READY,
    )
    root = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="dns_lookup",
        target_ref="example.com",
    )
    dependent = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        dependency_job_ids=[root.public_id],
    )

    first_pass = scheduler.run_once(now="2026-04-07T01:00:00+00:00")
    queued_root = job_service.require_job(root.public_id)
    pending_dependent = job_service.require_job(dependent.public_id)

    assert first_pass.queued_count == 1
    assert queued_root.status == JobStatus.QUEUED
    assert pending_dependent.status == JobStatus.PENDING

    queued_root.status = JobStatus.FAILED
    queued_root.finished_at = "2026-04-07T01:00:05+00:00"
    queued_root.last_error = "lookup failed"
    queued_root.updated_at = "2026-04-07T01:00:05+00:00"
    job_service.save_job(queued_root)

    second_pass = scheduler.run_once(now="2026-04-07T01:00:10+00:00")
    blocked_dependent = job_service.require_job(dependent.public_id)

    assert second_pass.blocked_count == 1
    assert blocked_dependent.status == JobStatus.BLOCKED
    assert "terminal failure" in (blocked_dependent.last_error or "")


def test_scheduler_recovers_stale_leases_with_retry_and_exhaustion(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    scheduler = Scheduler.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Recover stale leases",
        status=OperationStatus.READY,
    )
    retryable = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        retry_limit=1,
    )
    exhausted = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.org",
        retry_limit=1,
    )

    retryable.status = JobStatus.RUNNING
    retryable.lease_token = "lease-1"
    retryable.lease_owner = "worker-a"
    retryable.lease_expires_at = "2026-04-07T01:59:00+00:00"
    retryable.updated_at = "2026-04-07T01:58:00+00:00"
    job_service.save_job(retryable)

    exhausted.status = JobStatus.RUNNING
    exhausted.lease_token = "lease-2"
    exhausted.lease_owner = "worker-b"
    exhausted.lease_expires_at = "2026-04-07T01:59:00+00:00"
    exhausted.retry_count = 1
    exhausted.updated_at = "2026-04-07T01:58:00+00:00"
    job_service.save_job(exhausted)

    result = scheduler.run_once(now="2026-04-07T02:00:00+00:00")
    recovered_retryable = job_service.require_job(retryable.public_id)
    recovered_exhausted = job_service.require_job(exhausted.public_id)

    assert result.recovered_count == 2
    assert recovered_retryable.status == JobStatus.QUEUED
    assert recovered_retryable.retry_count == 1
    assert recovered_retryable.retry_after is not None
    assert recovered_exhausted.status == JobStatus.FAILED
    assert "lease expired" in (recovered_exhausted.last_error or "").lower()


def test_scheduler_scoped_pass_only_recovers_stale_leases_for_target_operation(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    scheduler = Scheduler.from_settings(settings)

    first_operation = operation_service.create_operation(
        title="Recon A",
        objective="Recover only this operation",
        status=OperationStatus.READY,
    )
    second_operation = operation_service.create_operation(
        title="Recon B",
        objective="Leave this operation alone",
        status=OperationStatus.READY,
    )
    first_job = job_service.create_job(
        operation_identifier=first_operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        retry_limit=1,
    )
    second_job = job_service.create_job(
        operation_identifier=second_operation.public_id,
        job_type="http_probe",
        target_ref="https://example.org",
        retry_limit=1,
    )

    for job in (first_job, second_job):
        job.status = JobStatus.RUNNING
        job.lease_token = f"lease-{job.public_id}"
        job.lease_owner = "worker-a"
        job.lease_expires_at = "2026-04-07T01:59:00+00:00"
        job.updated_at = "2026-04-07T01:58:00+00:00"
        job_service.save_job(job)

    result = scheduler.run_once(
        operation_identifier=first_operation.public_id,
        now="2026-04-07T02:00:00+00:00",
    )
    recovered_first = job_service.require_job(first_job.public_id)
    untouched_second = job_service.require_job(second_job.public_id)

    assert result.recovered_count == 1
    assert recovered_first.status == JobStatus.QUEUED
    assert untouched_second.status == JobStatus.RUNNING


def test_scheduler_cancels_queued_jobs_immediately(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    orchestration = JobOrchestrationService.from_settings(settings)
    scheduler = Scheduler.from_settings(settings)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Cancel queued work",
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    job.status = JobStatus.QUEUED
    job.queued_at = "2026-04-07T03:00:00+00:00"
    job.updated_at = "2026-04-07T03:00:00+00:00"
    job_service.save_job(job)

    orchestration.request_cancellation(job.public_id, reason="operator stop", now="2026-04-07T03:00:10+00:00")
    scheduler.run_once(now="2026-04-07T03:00:11+00:00")
    cancelled = job_service.require_job(job.public_id)

    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.last_error == "operator stop"


def test_worker_cancellation_wins_over_late_success(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    worker = WorkerRuntime.from_settings(settings, worker_id="worker-main")

    operation = operation_service.create_operation(
        title="Recon",
        objective="Prefer cancellation",
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    scheduler = Scheduler.from_settings(settings)
    scheduler.run_once(now="2026-04-07T04:00:00+00:00")

    def fake_execute_job(*, job_identifier: str, confirm=None):
        worker.job_service.request_cancellation(
            job_identifier,
            reason="operator stop",
            now="2026-04-07T04:00:02+00:00",
        )
        return ScopedExecutionResult(
            status="succeeded",
            message="late success",
            decision=None,
            result=None,
        )

    worker.execution_service.execute_job = fake_execute_job

    result = worker.run_once(now="2026-04-07T04:00:01+00:00")
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "cancelled"
    assert refreshed.status == JobStatus.CANCELLED


def test_worker_retries_then_times_out_when_budget_is_exhausted(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    worker = WorkerRuntime.from_settings(settings, worker_id="worker-main")

    operation = operation_service.create_operation(
        title="Recon",
        objective="Retry timeouts",
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
        retry_limit=1,
    )
    Scheduler.from_settings(settings).run_once(now="2026-04-07T05:00:00+00:00")

    def fake_timeout(*, job_identifier: str, confirm=None):
        return ScopedExecutionResult(
            status="timed_out",
            message="Execution timed out after 1 seconds.",
            decision=None,
            result=None,
        )

    worker.execution_service.execute_job = fake_timeout

    first = worker.run_once(now="2026-04-07T05:00:01+00:00")
    first_state = job_service.require_job(job.public_id)
    assert first.status == "requeued"
    assert first_state.status == JobStatus.QUEUED
    assert first_state.retry_count == 1

    first_state.retry_after = None
    first_state.updated_at = "2026-04-07T05:00:02+00:00"
    job_service.save_job(first_state)

    second = worker.run_once(now="2026-04-07T05:00:03+00:00")
    second_state = job_service.require_job(job.public_id)

    assert second.status == "timed_out"
    assert second_state.status == JobStatus.TIMED_OUT


def test_worker_drain_runs_multiple_independent_typed_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    worker = WorkerRuntime.from_settings(settings, worker_id="worker-main")

    server, thread = run_http_server()
    try:
        port = server.server_address[1]
        operation = operation_service.create_operation(
            title="Recon",
            objective="Drain queued work",
            allowed_hosts=["127.0.0.1"],
            allowed_protocols=["http"],
            allowed_ports=[port],
            allowed_tool_categories=["recon"],
            status=OperationStatus.READY,
        )
        first = job_service.create_job(
            operation_identifier=operation.public_id,
            job_type="http_probe",
            target_ref=f"http://127.0.0.1:{port}/first",
        )
        second = job_service.create_job(
            operation_identifier=operation.public_id,
            job_type="http_probe",
            target_ref=f"http://127.0.0.1:{port}/second",
        )

        drain = worker.drain()
        refreshed_first = job_service.require_job(first.public_id)
        refreshed_second = job_service.require_job(second.public_id)

        assert len(drain.run_results) == 2
        assert all(result.status == "succeeded" for result in drain.run_results)
        assert refreshed_first.status == JobStatus.SUCCEEDED
        assert refreshed_second.status == JobStatus.SUCCEEDED
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_worker_keeps_lease_alive_during_long_running_execution(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    worker = WorkerRuntime.from_settings(settings, worker_id="worker-main", lease_seconds=1)

    operation = operation_service.create_operation(
        title="Recon",
        objective="Keep heartbeating",
        status=OperationStatus.READY,
    )
    job = job_service.create_job(
        operation_identifier=operation.public_id,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    Scheduler.from_settings(settings).run_once(now="2026-04-07T06:00:00+00:00")

    heartbeat_calls: list[str] = []
    original_heartbeat = worker.job_service.heartbeat

    def wrapped_heartbeat(*, job_identifier: str, lease_token: str, lease_seconds: int, now: str | None = None):
        heartbeat_calls.append(now or "")
        return original_heartbeat(
            job_identifier=job_identifier,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            now=now,
        )

    monkeypatch.setattr(worker.job_service, "heartbeat", wrapped_heartbeat)

    def slow_execute_job(*, job_identifier: str, confirm=None):
        time.sleep(1.25)
        return ScopedExecutionResult(
            status="succeeded",
            message="ok",
            decision=None,
            result=None,
        )

    monkeypatch.setattr(worker.execution_service, "execute_job", slow_execute_job)

    result = worker.run_once(now="2026-04-07T06:00:01+00:00")
    refreshed = job_service.require_job(job.public_id)

    assert result.status == "succeeded"
    assert refreshed.status == JobStatus.SUCCEEDED
    assert len(heartbeat_calls) >= 3
