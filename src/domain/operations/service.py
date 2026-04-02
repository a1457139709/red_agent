from __future__ import annotations

from pathlib import Path

from domain.common import utc_now_iso
from domain.scope import ScopePolicyService
from storage.repositories import OperationRepository

from .artifacts import OperationArtifacts
from .models import Operation, OperationStatus


class OperationService:
    def __init__(
        self,
        repository: OperationRepository,
        scope_policy_service: ScopePolicyService,
        *,
        app_data_dir: Path,
    ) -> None:
        self.repository = repository
        self.scope_policy_service = scope_policy_service
        self.app_data_dir = Path(app_data_dir)

    def create_operation(
        self,
        *,
        title: str,
        objective: str,
        workspace: str,
        planner_profile: str | None = None,
        memory_profile_id: str | None = None,
    ) -> Operation:
        operation = Operation.create(
            title=title,
            objective=objective,
            workspace=workspace,
            planner_profile=planner_profile,
            memory_profile_id=memory_profile_id,
        )
        return self.repository.create(operation)

    def get_operation(self, identifier: str) -> Operation | None:
        return self.repository.get(identifier)

    def require_operation(self, identifier: str) -> Operation:
        operation = self.get_operation(identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {identifier}")
        return operation

    def list_operations(
        self,
        *,
        status: OperationStatus | None = None,
        limit: int | None = None,
    ) -> list[Operation]:
        return self.repository.list(status=status, limit=limit)

    def update_operation(self, operation: Operation) -> Operation:
        operation.updated_at = utc_now_iso()
        return self.repository.update(operation)

    def set_status(
        self,
        operation_id: str,
        status: OperationStatus,
        *,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> Operation:
        operation = self.require_operation(operation_id)
        operation.status = status
        operation.updated_at = utc_now_iso()
        operation.last_error_code = last_error_code
        operation.last_error_message = last_error_message
        if status in {OperationStatus.COMPLETED, OperationStatus.CANCELLED}:
            operation.closed_at = utc_now_iso()
        return self.repository.update(operation)

    def mark_ready(self, operation_id: str) -> Operation:
        operation = self.require_operation(operation_id)
        policy = self.scope_policy_service.get_policy(operation.id)
        if policy is None:
            raise ValueError("Operation cannot become ready without a scope policy")
        decision = self.scope_policy_service.validate_policy(policy)
        if not decision.allowed:
            raise ValueError(f"Operation cannot become ready: {decision.message}")
        operation.status = OperationStatus.READY
        operation.updated_at = utc_now_iso()
        return self.repository.update(operation)

    def delete_operation(self, operation_id: str) -> None:
        operation = self.require_operation(operation_id)
        self.repository.delete(operation.id)
        OperationArtifacts(self.app_data_dir, operation.id).delete()
