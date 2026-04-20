from __future__ import annotations

"""Legacy read-only operation adapter kept over session-owned storage."""

import warnings

from agent.settings import Settings, get_settings
from models.operation import Operation, OperationStatus
from models.scope_policy import ScopePolicy
from models.session import Session, SessionStatus
from storage.repositories.operations import OperationRepository
from storage.repositories.scope_policies import ScopePolicyRepository
from storage.sqlite import SQLiteStorage

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


def _session_to_operation_status(status: SessionStatus) -> OperationStatus:
    mapping = {
        SessionStatus.DRAFT: OperationStatus.DRAFT,
        SessionStatus.ACTIVE: OperationStatus.READY,
        SessionStatus.PAUSED: OperationStatus.PAUSED,
        SessionStatus.FAILED: OperationStatus.FAILED,
        SessionStatus.COMPLETED: OperationStatus.COMPLETED,
        SessionStatus.CANCELLED: OperationStatus.CANCELLED,
    }
    return mapping[SessionStatus(status)]


def project_session_to_operation(session: Session, policy: ScopePolicy) -> Operation:
    return Operation(
        id=session.id,
        public_id=session.public_id,
        title=session.title,
        objective=session.goal,
        workspace=session.workspace,
        scope_policy_id=policy.id,
        status=_session_to_operation_status(session.status),
        created_at=session.created_at,
        updated_at=session.updated_at,
        closed_at=session.closed_at,
        last_error=session.last_error,
    )


class OperationService:
    def __init__(
        self,
        operation_repository: OperationRepository,
        scope_policy_repository: ScopePolicyRepository,
        session_service: SessionService,
        settings: Settings,
    ) -> None:
        self.operation_repository = operation_repository
        self.scope_policy_repository = scope_policy_repository
        self.session_service = session_service
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
            settings,
        )

    def get_operation(self, identifier: str) -> Operation | None:
        operation = self.operation_repository.get(identifier)
        if operation is not None:
            return operation

        session = self.session_service.get_session(identifier)
        if session is None:
            return None

        policy = self.scope_policy_repository.get_by_session_id(session.id)
        if policy is None:
            return None
        return project_session_to_operation(session, policy)

    def require_operation(self, identifier: str) -> Operation:
        operation = self.get_operation(identifier)
        if operation is None:
            raise ValueError(f"Operation not found: {identifier}")
        return operation

    def get_scope_policy(self, operation_identifier: str) -> ScopePolicy | None:
        warnings.warn(
            "OperationService.get_scope_policy() is deprecated as a scope-policy access path. "
            "Use ScopePolicyService.get_scope_policy_for_session() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        operation = self.get_operation(operation_identifier)
        if operation is None:
            return None
        return self.scope_policy_repository.get_by_session_id(operation.id)

    def require_scope_policy(self, operation_identifier: str) -> ScopePolicy:
        warnings.warn(
            "OperationService.require_scope_policy() is deprecated as a scope-policy access path. "
            "Use ScopePolicyService.require_scope_policy_for_session() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        policy = self.get_scope_policy(operation_identifier)
        if policy is None:
            raise ValueError(f"Scope policy not found for operation: {operation_identifier}")
        return policy
