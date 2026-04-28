from __future__ import annotations

from app.session_service import SessionService
from storage.repositories.operations import OperationRepository


def resolve_session_identifier(
    session_service: SessionService,
    identifier: str,
    *,
    operation_repository: OperationRepository | None = None,
) -> str:
    session = session_service.get_session(identifier)
    if session is not None:
        return session.id

    if operation_repository is not None:
        operation = operation_repository.get(identifier)
        if operation is not None:
            return operation.id

    raise ValueError(f"Session not found: {identifier}")
