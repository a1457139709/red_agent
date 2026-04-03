from __future__ import annotations

from agent.settings import Settings, get_settings
from models.scope_policy import ScopePolicy
from storage.repositories.scope_policies import ScopePolicyRepository
from storage.sqlite import SQLiteStorage


def _ensure_positive_int(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")


class ScopePolicyService:
    def __init__(self, repository: ScopePolicyRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ScopePolicyService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(ScopePolicyRepository(storage), settings)

    def create_scope_policy(
        self,
        *,
        operation_id: str,
        allowed_hosts: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        allowed_cidrs: list[str] | None = None,
        allowed_ports: list[int] | None = None,
        allowed_protocols: list[str] | None = None,
        denied_targets: list[str] | None = None,
        allowed_tool_categories: list[str] | None = None,
        max_concurrency: int = 1,
        rate_limit_per_minute: int | None = None,
        confirmation_required_actions: list[str] | None = None,
    ) -> ScopePolicy:
        _ensure_positive_int(max_concurrency, field_name="max_concurrency")
        if rate_limit_per_minute is not None:
            _ensure_positive_int(rate_limit_per_minute, field_name="rate_limit_per_minute")

        policy = ScopePolicy.create(
            operation_id=operation_id,
            allowed_hosts=allowed_hosts,
            allowed_domains=allowed_domains,
            allowed_cidrs=allowed_cidrs,
            allowed_ports=allowed_ports,
            allowed_protocols=allowed_protocols,
            denied_targets=denied_targets,
            allowed_tool_categories=allowed_tool_categories,
            max_concurrency=max_concurrency,
            rate_limit_per_minute=rate_limit_per_minute,
            confirmation_required_actions=confirmation_required_actions,
        )
        return self.repository.create(policy)

    def get_scope_policy(self, policy_id: str) -> ScopePolicy | None:
        return self.repository.get(policy_id)

    def get_scope_policy_for_operation(self, operation_id: str) -> ScopePolicy | None:
        return self.repository.get_by_operation_id(operation_id)

    def require_scope_policy(self, policy_id: str) -> ScopePolicy:
        policy = self.get_scope_policy(policy_id)
        if policy is None:
            raise ValueError(f"Scope policy not found: {policy_id}")
        return policy

    def list_scope_policies(self, *, limit: int | None = 50) -> list[ScopePolicy]:
        return self.repository.list(limit=limit)

    def save_scope_policy(self, policy: ScopePolicy) -> ScopePolicy:
        if policy.max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than 0.")
        if policy.rate_limit_per_minute is not None and policy.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be greater than 0.")
        return self.repository.update(policy)
