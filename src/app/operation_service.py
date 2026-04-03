from __future__ import annotations

from agent.settings import Settings, get_settings
from models.operation import Operation, OperationStatus
from models.scope_policy import ScopePolicy
from storage.repositories.operations import OperationRepository
from storage.repositories.scope_policies import ScopePolicyRepository
from storage.sqlite import SQLiteStorage


def _ensure_positive_int(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")


class OperationService:
    def __init__(
        self,
        operation_repository: OperationRepository,
        scope_policy_repository: ScopePolicyRepository,
        settings: Settings,
    ) -> None:
        self.operation_repository = operation_repository
        self.scope_policy_repository = scope_policy_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OperationService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            OperationRepository(storage),
            ScopePolicyRepository(storage),
            settings,
        )

    def create_operation(
        self,
        *,
        title: str,
        objective: str,
        workspace: str | None = None,
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
        status: OperationStatus = OperationStatus.DRAFT,
    ) -> Operation:
        _ensure_positive_int(max_concurrency, field_name="max_concurrency")
        if rate_limit_per_minute is not None:
            _ensure_positive_int(rate_limit_per_minute, field_name="rate_limit_per_minute")

        scope_policy_id = ScopePolicy.create(operation_id="pending").id
        operation = Operation.create(
            title=title,
            objective=objective,
            workspace=workspace or str(self.settings.working_directory),
            scope_policy_id=scope_policy_id,
            status=status,
        )
        policy = ScopePolicy(
            id=scope_policy_id,
            operation_id=operation.id,
            allowed_hosts=list(allowed_hosts or []),
            allowed_domains=list(allowed_domains or []),
            allowed_cidrs=list(allowed_cidrs or []),
            allowed_ports=list(allowed_ports or []),
            allowed_protocols=list(allowed_protocols or []),
            denied_targets=list(denied_targets or []),
            allowed_tool_categories=list(allowed_tool_categories or []),
            max_concurrency=max_concurrency,
            rate_limit_per_minute=rate_limit_per_minute,
            confirmation_required_actions=list(confirmation_required_actions or []),
        )

        storage = self.operation_repository.storage
        with storage.connect() as connection:
            self.operation_repository._create_with_connection(connection, operation)
            self.scope_policy_repository._create_with_connection(connection, policy)
            connection.commit()
        return operation

    def get_operation(self, identifier: str) -> Operation | None:
        return self.operation_repository.get(identifier)

    def require_operation(self, identifier: str) -> Operation:
        operation = self.get_operation(identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {identifier}")
        return operation

    def list_operations(
        self,
        *,
        status: OperationStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Operation]:
        return self.operation_repository.list(status=status, title_query=title_query, limit=limit)

    def save_operation(self, operation: Operation) -> Operation:
        return self.operation_repository.update(operation)

    def get_scope_policy(self, operation_identifier: str) -> ScopePolicy | None:
        operation = self.get_operation(operation_identifier)
        if operation is None:
            return None
        return self.scope_policy_repository.get(operation.scope_policy_id)

    def require_scope_policy(self, operation_identifier: str) -> ScopePolicy:
        policy = self.get_scope_policy(operation_identifier)
        if policy is None:
            raise ValueError(f"Scope policy not found for operation: {operation_identifier}")
        return policy
