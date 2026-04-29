from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.scope_policy_service import ScopePolicyService
from app.session_scope import resolve_session_identifier
from app.session_event_service import SessionEventService
from models.job import Job
from models.session import Session, SessionStatus
from models.session_event import SessionEventLevel, SessionEventType
from models.scope_policy import ScopePolicy
from storage.repositories.jobs import JobRepository
from app.session_service import SessionService

from .rate_limits import SessionRateLimiter
from .scope_validator import AdmissionDecision, AdmissionRequest, ScopeValidator, TargetDescriptor


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    session: Session
    policy: ScopePolicy
    job: Job | None
    target: TargetDescriptor
    decision: AdmissionDecision


class SessionAdmissionService:
    RUNNABLE_SESSION_STATUSES = frozenset({SessionStatus.ACTIVE})

    def __init__(
        self,
        session_service: SessionService,
        scope_policy_service: ScopePolicyService,
        job_repository: JobRepository,
        session_event_service: SessionEventService,
        scope_validator: ScopeValidator | None = None,
        rate_limiter: SessionRateLimiter | None = None,
    ) -> None:
        self.session_service = session_service
        self.scope_policy_service = scope_policy_service
        self.job_repository = job_repository
        self.session_event_service = session_event_service
        self.scope_validator = scope_validator or ScopeValidator()
        self.rate_limiter = rate_limiter or SessionRateLimiter()

    def admit(self, request: AdmissionRequest) -> AdmissionContext:
        session_id = resolve_session_identifier(
            self.session_service,
            request.session_id,
        )
        session = self.session_service.require_session(session_id)
        policy = self.scope_policy_service.require_scope_policy_for_session(session.id)
        job = self._load_job(request, session.id)
        target = self._describe_target_for_audit(request)

        self.session_event_service.create_event(
            session_identifier=session.id,
            job_identifier=job.id if job is not None else None,
            event_type=SessionEventType.ADMISSION_REQUESTED,
            level=SessionEventLevel.INFO,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            target_ref=target.normalized_target,
            message="Admission requested for scoped execution.",
            payload=self._event_payload(request, target),
        )

        decision = self._check_session_status(session, target)
        if decision is None:
            decision = self.scope_validator.evaluate(policy, request)
            target = decision.target

        if decision.outcome == "allowed":
            concurrency_denial = self.rate_limiter.check_concurrency(
                policy=policy,
                running_jobs=self.job_repository.count_running(
                    session.id,
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
                    session.id,
                    event_type=SessionEventType.EXECUTION_STARTED,
                    since=cutoff.isoformat(),
                ),
                target=target,
            )
            if rate_limit_denial is not None:
                decision = rate_limit_denial

        if decision.outcome == "denied":
            self.session_event_service.create_event(
                session_identifier=session.id,
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
            session=session,
            policy=policy,
            job=job,
            target=target,
            decision=decision,
        )

    def _load_job(self, request: AdmissionRequest, session_id: str) -> Job | None:
        if request.job_id is None:
            return None
        job = self.job_repository.get(request.job_id)
        if job is None:
            raise ValueError(f"Job not found: {request.job_id}")
        if job.session_id != session_id:
            raise ValueError("Job must belong to the same session as the admission request.")
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

    def _check_session_status(
        self,
        session: Session,
        target: TargetDescriptor,
    ) -> AdmissionDecision | None:
        if session.status in self.RUNNABLE_SESSION_STATUSES:
            return None
        return AdmissionDecision(
            outcome="denied",
            reason_code="session_not_runnable",
            message=(
                f"Session '{session.public_id or session.id}' is in status "
                f"'{session.status.value}' and cannot execute scoped work."
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
