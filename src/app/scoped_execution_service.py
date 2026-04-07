from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from agent.settings import Settings, get_settings
from models.job import Job, JobStatus
from models.operation_event import OperationEventLevel, OperationEventType
from models.run import utc_now_iso
from orchestration.admission import AdmissionContext, OperationAdmissionService
from orchestration.scope_validator import AdmissionDecision, AdmissionOutcome, AdmissionRequest, TargetDescriptor
from storage.repositories.jobs import JobRepository
from storage.sqlite import SQLiteStorage

from .operation_event_service import OperationEventService
from .operation_service import OperationService


ConfirmCallback = Callable[[str], bool] | None
ScopedExecutor = Callable[[AdmissionRequest, TargetDescriptor], object]


@dataclass(frozen=True, slots=True)
class ScopedExecutionResult:
    status: str
    message: str
    decision: AdmissionDecision
    result: object | None = None


class ScopedExecutionService:
    def __init__(
        self,
        admission_service: OperationAdmissionService,
        job_repository: JobRepository,
        operation_event_service: OperationEventService,
        settings: Settings,
    ) -> None:
        self.admission_service = admission_service
        self.job_repository = job_repository
        self.operation_event_service = operation_event_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ScopedExecutionService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        operation_service = OperationService.from_settings(settings)
        operation_event_service = OperationEventService.from_settings(settings)
        job_repository = JobRepository(storage)
        return cls(
            admission_service=OperationAdmissionService(
                operation_service=operation_service,
                job_repository=job_repository,
                operation_event_service=operation_event_service,
            ),
            job_repository=job_repository,
            operation_event_service=operation_event_service,
            settings=settings,
        )

    def execute(
        self,
        *,
        request: AdmissionRequest,
        executor: ScopedExecutor,
        confirm: ConfirmCallback = None,
    ) -> ScopedExecutionResult:
        context = self.admission_service.admit(request)
        decision = context.decision

        if decision.outcome == AdmissionOutcome.DENIED:
            self._block_job(context.job, decision.message)
            return ScopedExecutionResult(
                status="blocked",
                message=decision.message,
                decision=decision,
            )

        if decision.outcome == AdmissionOutcome.REQUIRES_CONFIRMATION:
            confirmation_result = self._handle_confirmation(context, request, confirm)
            if confirmation_result is not None:
                return confirmation_result
            context = self._recheck_after_confirmation(context, request)
            decision = context.decision
            if decision.outcome == AdmissionOutcome.DENIED:
                self._block_job(context.job, decision.message)
                return ScopedExecutionResult(
                    status="blocked",
                    message=decision.message,
                    decision=decision,
                )

        self._mark_job_running(context.job)
        self.operation_event_service.create_event(
            operation_identifier=context.operation.id,
            job_identifier=context.job.id if context.job is not None else None,
            event_type=OperationEventType.EXECUTION_STARTED,
            level=OperationEventLevel.INFO,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            target_ref=context.target.normalized_target,
            message="Scoped execution started.",
            payload=self._event_payload(request, context.target),
        )

        try:
            result = executor(request, context.target)
        except Exception as exc:
            error = str(exc)
            self._fail_job(context.job, error)
            self.operation_event_service.create_event(
                operation_identifier=context.operation.id,
                job_identifier=context.job.id if context.job is not None else None,
                event_type=OperationEventType.EXECUTION_FAILED,
                level=OperationEventLevel.ERROR,
                tool_name=request.tool_name,
                tool_category=request.tool_category,
                target_ref=context.target.normalized_target,
                message=error,
                payload={**self._event_payload(request, context.target), "error": error},
            )
            return ScopedExecutionResult(
                status="failed",
                message=error,
                decision=decision,
            )

        self._succeed_job(context.job)
        self.operation_event_service.create_event(
            operation_identifier=context.operation.id,
            job_identifier=context.job.id if context.job is not None else None,
            event_type=OperationEventType.EXECUTION_SUCCEEDED,
            level=OperationEventLevel.INFO,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            target_ref=context.target.normalized_target,
            message="Scoped execution succeeded.",
            payload={
                **self._event_payload(request, context.target),
                "result_summary": self._summarize_result(result),
            },
        )
        return ScopedExecutionResult(
            status="succeeded",
            message="Scoped execution succeeded.",
            decision=decision,
            result=result,
        )

    def _handle_confirmation(
        self,
        context: AdmissionContext,
        request: AdmissionRequest,
        confirm: ConfirmCallback,
    ) -> ScopedExecutionResult | None:
        self.operation_event_service.create_event(
            operation_identifier=context.operation.id,
            job_identifier=context.job.id if context.job is not None else None,
            event_type=OperationEventType.CONFIRMATION_REQUIRED,
            level=OperationEventLevel.INFO,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            target_ref=context.target.normalized_target,
            message=context.decision.message,
            payload=self._event_payload(request, context.target),
        )

        if confirm is None:
            decision = AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="confirmation_unavailable",
                message="Operator confirmation is required but no confirmation handler is available.",
                target=context.target,
            )
            self._block_job(context.job, decision.message)
            self.operation_event_service.create_event(
                operation_identifier=context.operation.id,
                job_identifier=context.job.id if context.job is not None else None,
                event_type=OperationEventType.CONFIRMATION_DENIED,
                level=OperationEventLevel.ERROR,
                tool_name=request.tool_name,
                tool_category=request.tool_category,
                target_ref=context.target.normalized_target,
                reason_code=decision.reason_code,
                message=decision.message,
                payload=self._event_payload(request, context.target),
            )
            return ScopedExecutionResult(status="blocked", message=decision.message, decision=decision)

        prompt = (
            f"{context.decision.message}\n"
            f"Target: {context.target.normalized_target}\n"
            f"Tool: {request.tool_name}"
        )
        if not confirm(prompt):
            decision = AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="confirmation_declined",
                message="Operator declined the required confirmation.",
                target=context.target,
            )
            self._block_job(context.job, decision.message)
            self.operation_event_service.create_event(
                operation_identifier=context.operation.id,
                job_identifier=context.job.id if context.job is not None else None,
                event_type=OperationEventType.CONFIRMATION_DENIED,
                level=OperationEventLevel.ERROR,
                tool_name=request.tool_name,
                tool_category=request.tool_category,
                target_ref=context.target.normalized_target,
                reason_code=decision.reason_code,
                message=decision.message,
                payload=self._event_payload(request, context.target),
            )
            return ScopedExecutionResult(status="blocked", message=decision.message, decision=decision)

        self.operation_event_service.create_event(
            operation_identifier=context.operation.id,
            job_identifier=context.job.id if context.job is not None else None,
            event_type=OperationEventType.CONFIRMATION_APPROVED,
            level=OperationEventLevel.INFO,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            target_ref=context.target.normalized_target,
            message="Operator approved the scoped execution request.",
            payload=self._event_payload(request, context.target),
        )
        return None

    def _recheck_after_confirmation(
        self,
        context: AdmissionContext,
        request: AdmissionRequest,
    ) -> AdmissionContext:
        recheck_request = replace(
            request,
            skip_confirmation=True,
            admission_stage="post_confirmation_recheck",
        )
        rechecked_context = self.admission_service.admit(recheck_request)
        return AdmissionContext(
            operation=rechecked_context.operation,
            policy=rechecked_context.policy,
            job=rechecked_context.job,
            target=rechecked_context.target,
            decision=rechecked_context.decision,
        )

    def _mark_job_running(self, job: Job | None) -> None:
        if job is None:
            return
        now = utc_now_iso()
        job.status = JobStatus.RUNNING
        job.started_at = now
        job.finished_at = None
        job.last_error = None
        job.updated_at = now
        self.job_repository.update(job)

    def _block_job(self, job: Job | None, message: str) -> None:
        if job is None:
            return
        now = utc_now_iso()
        job.status = JobStatus.BLOCKED
        job.finished_at = now
        job.last_error = message
        job.updated_at = now
        self.job_repository.update(job)

    def _fail_job(self, job: Job | None, message: str) -> None:
        if job is None:
            return
        now = utc_now_iso()
        if job.started_at is None:
            job.started_at = now
        job.status = JobStatus.FAILED
        job.finished_at = now
        job.last_error = message
        job.updated_at = now
        self.job_repository.update(job)

    def _succeed_job(self, job: Job | None) -> None:
        if job is None:
            return
        now = utc_now_iso()
        if job.started_at is None:
            job.started_at = now
        job.status = JobStatus.SUCCEEDED
        job.finished_at = now
        job.last_error = None
        job.updated_at = now
        self.job_repository.update(job)

    def _event_payload(self, request: AdmissionRequest, target: TargetDescriptor) -> dict[str, Any]:
        return {
            "raw_target": request.raw_target,
            "normalized_target": target.normalized_target,
            "protocol": target.protocol,
            "port": target.port,
            "metadata": request.metadata,
            "admission_stage": request.admission_stage,
            "skip_confirmation": request.skip_confirmation,
            "additional_targets": [
                {
                    "raw_target": additional_target.raw_target,
                    "protocol": additional_target.protocol,
                    "port": additional_target.port,
                    "label": additional_target.label,
                }
                for additional_target in request.additional_targets
            ],
        }

    def _summarize_result(self, result: object) -> str:
        text = str(result)
        if len(text) <= 200:
            return text
        return text[:197] + "..."
