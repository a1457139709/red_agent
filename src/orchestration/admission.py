from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.operation_service import OperationService
from app.scope_policy_service import ScopePolicyService
from app.session_event_service import SessionEventService
from models.job import Job
from models.operation import Operation, OperationStatus
from models.session_event import SessionEventLevel, SessionEventType
from models.scope_policy import ScopePolicy
from storage.repositories.jobs import JobRepository

from .rate_limits import OperationRateLimiter
from .scope_validator import AdmissionDecision, AdmissionRequest, ScopeValidator, TargetDescriptor


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    operation: Operation
    policy: ScopePolicy
    job: Job | None
    target: TargetDescriptor
    decision: AdmissionDecision


class OperationAdmissionService:
    RUNNABLE_OPERATION_STATUSES = frozenset({OperationStatus.READY, OperationStatus.RUNNING})

    def __init__(
        self,
        operation_service: OperationService,
        scope_policy_service: ScopePolicyService,
        job_repository: JobRepository,
        session_event_service: SessionEventService,
        scope_validator: ScopeValidator | None = None,
        rate_limiter: OperationRateLimiter | None = None,
    ) -> None:
        self.operation_service = operation_service
        self.scope_policy_service = scope_policy_service
        self.job_repository = job_repository
        self.session_event_service = session_event_service
        self.scope_validator = scope_validator or ScopeValidator()
        self.rate_limiter = rate_limiter or OperationRateLimiter()

    def admit(self, request: AdmissionRequest) -> AdmissionContext:
        operation = self.operation_service.require_operation(request.operation_id)
        policy = self.scope_policy_service.require_scope_policy_for_session(operation.id)
        job = self._load_job(request, operation.id)
        target = self._describe_target_for_audit(request)

        self.session_event_service.create_event(
            operation_identifier=operation.id,
            job_identifier=job.id if job is not None else None,
            event_type=SessionEventType.ADMISSION_REQUESTED,
            level=SessionEventLevel.INFO,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            target_ref=target.normalized_target,
            message="Admission requested for scoped execution.",
            payload=self._event_payload(request, target),
        )

        decision = self._check_operation_status(operation, target)
        if decision is None:
            decision = self.scope_validator.evaluate(policy, request)
            target = decision.target

        if decision.outcome == "allowed":
            concurrency_denial = self.rate_limiter.check_concurrency(
                policy=policy,
                running_jobs=self.job_repository.count_running(
                    operation.id,
                    exclude_job_id=job.id if job is not None else None,
                ),
                target=target,
            )
            if concurrency_denial is not None:
                decision = concurrency_denial

        if decision.outcome == "allowed":
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
            rate_limit_denial = self.rate_limiter.check_rate_limit(
                policy=policy,
                recent_executions=self.session_event_service.count_events_since(
                    operation.id,
                    event_type=SessionEventType.EXECUTION_STARTED,
                    since=cutoff.isoformat(),
                ),
                target=target,
            )
            if rate_limit_denial is not None:
                decision = rate_limit_denial

        if decision.outcome == "denied":
            self.session_event_service.create_event(
                operation_identifier=operation.id,
                job_identifier=job.id if job is not None else None,
                event_type=SessionEventType.ADMISSION_DENIED,
                level=SessionEventLevel.ERROR,
                tool_name=request.tool_name,
                tool_category=request.tool_category,
                target_ref=target.normalized_target,
                reason_code=decision.reason_code,
                message=decision.message,
                payload=self._event_payload(request, target),
            )

        return AdmissionContext(
            operation=operation,
            policy=policy,
            job=job,
            target=target,
            decision=decision,
        )

    def _load_job(self, request: AdmissionRequest, operation_id: str) -> Job | None:
        if request.job_id is None:
            return None
        job = self.job_repository.get(request.job_id)
        if job is None:
            raise ValueError(f"Job not found: {request.job_id}")
        if job.operation_id != operation_id:
            raise ValueError("Job must belong to the same operation as the admission request.")
        return job

    def _describe_target_for_audit(self, request: AdmissionRequest) -> TargetDescriptor:
        try:
            return self.scope_validator.describe_target(request)
        except ValueError:
            return TargetDescriptor(
                raw_target=request.raw_target,
                kind="unknown",
                host=None,
                ip=None,
                port=request.port,
                protocol=request.protocol,
                normalized_target=request.raw_target.strip() or request.raw_target,
            )

    def _check_operation_status(
        self,
        operation: Operation,
        target: TargetDescriptor,
    ) -> AdmissionDecision | None:
        if operation.status in self.RUNNABLE_OPERATION_STATUSES:
            return None
        return AdmissionDecision(
            outcome="denied",
            reason_code="operation_not_runnable",
            message=(
                f"Operation '{operation.public_id or operation.id}' is in status "
                f"'{operation.status.value}' and cannot execute scoped work."
            ),
            target=target,
        )

    def _event_payload(self, request: AdmissionRequest, target: TargetDescriptor) -> dict[str, object]:
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
