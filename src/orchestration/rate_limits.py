from __future__ import annotations

from dataclasses import dataclass

from models.scope_policy import ScopePolicy

from .scope_validator import AdmissionDecision, AdmissionOutcome, TargetDescriptor


@dataclass(frozen=True, slots=True)
class OperationRateLimiter:
    def check_concurrency(
        self,
        *,
        policy: ScopePolicy,
        running_jobs: int,
        target: TargetDescriptor,
    ) -> AdmissionDecision | None:
        if policy.max_concurrency <= 0:
            return None
        if running_jobs < policy.max_concurrency:
            return None
        return AdmissionDecision(
            outcome=AdmissionOutcome.DENIED,
            reason_code="max_concurrency_exceeded",
            message=(
                f"Operation has reached its concurrency limit "
                f"({running_jobs}/{policy.max_concurrency})."
            ),
            target=target,
        )

    def check_rate_limit(
        self,
        *,
        policy: ScopePolicy,
        recent_executions: int,
        target: TargetDescriptor,
    ) -> AdmissionDecision | None:
        if policy.rate_limit_per_minute is None:
            return None
        if recent_executions < policy.rate_limit_per_minute:
            return None
        return AdmissionDecision(
            outcome=AdmissionOutcome.DENIED,
            reason_code="rate_limit_exceeded",
            message=(
                f"Operation has reached its rate limit "
                f"({recent_executions}/{policy.rate_limit_per_minute} executions per minute)."
            ),
            target=target,
        )
