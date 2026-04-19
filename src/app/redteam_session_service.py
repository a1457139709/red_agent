from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings, get_settings
from models.operation import Operation, OperationStatus
from models.scope_policy import ScopePolicy
from models.session import (
    Session,
    SessionMode,
    SessionPersistenceMode,
    SessionStatus,
    SessionTarget,
    SessionTargetKind,
)
from storage.repositories.operations import OperationRepository
from storage.repositories.scope_policies import ScopePolicyRepository
from storage.sqlite import SQLiteStorage

from .session_service import SessionService


def _ensure_positive_int(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")


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


def _build_targets(
    *,
    allowed_hosts: list[str] | None,
    allowed_domains: list[str] | None,
    allowed_cidrs: list[str] | None,
) -> list[SessionTarget]:
    targets: list[SessionTarget] = []
    for value in allowed_domains or []:
        targets.append(SessionTarget(kind=SessionTargetKind.DOMAIN, value=value))
    for value in allowed_hosts or []:
        targets.append(SessionTarget(kind=SessionTargetKind.HOST, value=value))
    for value in allowed_cidrs or []:
        targets.append(SessionTarget(kind=SessionTargetKind.CIDR, value=value))
    return targets


@dataclass(frozen=True, slots=True)
class RedteamSessionBundle:
    session: Session
    operation: Operation
    scope_policy: ScopePolicy


class RedteamSessionService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        operation_repository: OperationRepository,
        scope_policy_repository: ScopePolicyRepository,
        settings: Settings,
    ) -> None:
        self.session_service = session_service
        self.operation_repository = operation_repository
        self.scope_policy_repository = scope_policy_repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "RedteamSessionService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            session_service=SessionService.from_settings(settings),
            operation_repository=OperationRepository(storage),
            scope_policy_repository=ScopePolicyRepository(storage),
            settings=settings,
        )

    def create_redteam_session(
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
    ) -> RedteamSessionBundle:
        _ensure_positive_int(max_concurrency, field_name="max_concurrency")
        if rate_limit_per_minute is not None:
            _ensure_positive_int(rate_limit_per_minute, field_name="rate_limit_per_minute")

        session = self.session_service.create_session(
            title=title,
            goal=objective,
            mode=SessionMode.REDTEAM,
            persistence_mode=SessionPersistenceMode.PERSISTENT,
            workspace=workspace or str(self.settings.working_directory),
            targets=_build_targets(
                allowed_hosts=allowed_hosts,
                allowed_domains=allowed_domains,
                allowed_cidrs=allowed_cidrs,
            ),
            status=_operation_to_session_status(status),
            metadata={"legacy_container": "operation_projection"},
        )
        scope_policy = ScopePolicy.create(
            session_id=session.id,
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
        operation = Operation(
            id=session.id,
            public_id="",
            title=title,
            objective=objective,
            workspace=session.workspace,
            scope_policy_id=scope_policy.id,
            status=status,
        )

        storage = self.operation_repository.storage
        with storage.connect() as connection:
            self.operation_repository._create_with_connection(connection, operation)
            self.scope_policy_repository._create_with_connection(connection, scope_policy)
            connection.commit()

        return RedteamSessionBundle(
            session=session,
            operation=operation,
            scope_policy=scope_policy,
        )
