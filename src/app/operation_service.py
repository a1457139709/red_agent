from __future__ import annotations

"""Legacy top-level operation service kept as a thin wrapper over session-owned storage."""

import warnings

from agent.settings import Settings, get_settings
from models.operation import Operation, OperationStatus
from models.scope_policy import ScopePolicy
from models.run import utc_now_iso
from models.session import SessionStatus
from storage.repositories.operations import OperationRepository
from storage.repositories.scope_policies import ScopePolicyRepository
from storage.sqlite import SQLiteStorage

from .redteam_session_service import RedteamSessionService
from .session_service import SessionService


def _operation_to_session_status(status: OperationStatus) -> SessionStatus:
    mapping = {
        OperationStatus.DRAFT: SessionStatus.DRAFT,
        OperationStatus.READY: SessionStatus.ACTIVE,
        OperationStatus.RUNNING: SessionStatus.ACTIVE,
        OperationStatus.PAUSED: SessionStatus.PAUSED,
        OperationStatus.BLOCKED: SessionStatus.ACTIVE,
        OperationStatus.FAILED: SessionStatus.FAILED,
        OperationStatus.COMPLETED: SessionStatus.COMPLETED,
        OperationStatus.CANCELLED: SessionStatus.CANCELLED,
    }
    return mapping[OperationStatus(status)]


class OperationService:
    def __init__(
        self,
        operation_repository: OperationRepository,
        scope_policy_repository: ScopePolicyRepository,
        session_service: SessionService,
        redteam_session_service: RedteamSessionService,
        settings: Settings,
    ) -> None:
        self.operation_repository = operation_repository
        self.scope_policy_repository = scope_policy_repository
        self.session_service = session_service
        self.redteam_session_service = redteam_session_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OperationService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        session_service = SessionService.from_settings(settings)
        return cls(
            OperationRepository(storage),
            ScopePolicyRepository(storage),
            session_service,
            RedteamSessionService(
                session_service=session_service,
                operation_repository=OperationRepository(storage),
                scope_policy_repository=ScopePolicyRepository(storage),
                settings=settings,
            ),
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
        warnings.warn(
            "OperationService.create_operation() is deprecated as a primary write path. "
            "Use RedteamSessionService.create_redteam_session() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        bundle = self.redteam_session_service.create_redteam_session(
            title=title,
            objective=objective,
            workspace=workspace,
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
            status=status,
        )
        return bundle.operation

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
        stored = self.operation_repository.update(operation)
        self._sync_session_from_operation(stored)
        return stored

    def pause_operation(self, identifier: str) -> Operation:
        operation = self.require_operation(identifier)
        if operation.status not in {
            OperationStatus.READY,
            OperationStatus.RUNNING,
            OperationStatus.BLOCKED,
        }:
            raise ValueError("Operations can only be paused from ready, running, or blocked status.")
        operation.status = OperationStatus.PAUSED
        operation.updated_at = utc_now_iso()
        self._sync_session_from_operation(operation)
        return self.operation_repository.update(operation)

    def resume_operation(self, identifier: str) -> Operation:
        operation = self.require_operation(identifier)
        if operation.status in {
            OperationStatus.COMPLETED,
            OperationStatus.CANCELLED,
            OperationStatus.FAILED,
        }:
            raise ValueError(
                f"Operation {operation.public_id or operation.id} cannot be resumed from status "
                f"{operation.status.value}."
            )
        if operation.status not in {
            OperationStatus.DRAFT,
            OperationStatus.PAUSED,
            OperationStatus.BLOCKED,
        }:
            raise ValueError("Operations can only be resumed from draft, paused, or blocked status.")
        operation.status = OperationStatus.READY
        operation.updated_at = utc_now_iso()
        self._sync_session_from_operation(operation)
        return self.operation_repository.update(operation)

    def get_scope_policy(self, operation_identifier: str) -> ScopePolicy | None:
        operation = self.get_operation(operation_identifier)
        if operation is None:
            return None
        return self.scope_policy_repository.get_by_session_id(operation.id)

    def require_scope_policy(self, operation_identifier: str) -> ScopePolicy:
        policy = self.get_scope_policy(operation_identifier)
        if policy is None:
            raise ValueError(f"Scope policy not found for operation: {operation_identifier}")
        return policy

    def _sync_session_from_operation(self, operation: Operation) -> None:
        session = self.session_service.require_session(operation.id)
        session.title = operation.title
        session.goal = operation.objective
        session.workspace = operation.workspace
        session.last_error = operation.last_error
        session.status = _operation_to_session_status(operation.status)
        self.session_service.save_session(session)
