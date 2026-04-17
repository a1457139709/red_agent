from __future__ import annotations

from app.session_service import SessionService
from storage.repositories.operations import OperationRepository
from storage.tasks import TaskRepository


def resolve_session_identifier(
    session_service: SessionService,
    identifier: str,
    *,
    operation_repository: OperationRepository | None = None,
    task_repository: TaskRepository | None = None,
) -> str:
    session = session_service.get_session(identifier)
    if session is not None:
        return session.id

    if operation_repository is not None:
        operation = operation_repository.get(identifier)
        if operation is not None:
            return operation.id

    if task_repository is not None:
        task = task_repository.get(identifier)
        if task is not None and task.session_id:
            return task.session_id

    raise ValueError(f"Session not found: {identifier}")
