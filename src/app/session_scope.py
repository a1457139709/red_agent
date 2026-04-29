from __future__ import annotations

from app.session_service import SessionService


def resolve_session_identifier(
    session_service: SessionService,
    identifier: str,
) -> str:
    session = session_service.get_session(identifier)
    if session is not None:
        return session.id

    raise ValueError(f"Session not found: {identifier}")
