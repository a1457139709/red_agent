from __future__ import annotations

from typing import Any

from agent.settings import Settings, get_settings
from models.run import utc_now_iso
from models.session import (
    Session,
    SessionMode,
    SessionPersistenceMode,
    SessionStatus,
    SessionTarget,
    TERMINAL_SESSION_STATUSES,
)
from storage.repositories.sessions import SessionRepository
from storage.sqlite import SQLiteStorage


_UNSET = object()


def _default_persistence_mode(mode: SessionMode) -> SessionPersistenceMode:
    if mode == SessionMode.REDTEAM:
        return SessionPersistenceMode.PERSISTENT
    return SessionPersistenceMode.EPHEMERAL


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SessionService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(SessionRepository(storage), settings)

    def create_session(
        self,
        *,
        title: str,
        goal: str,
        mode: SessionMode,
        persistence_mode: SessionPersistenceMode | None = None,
        workspace: str | None = None,
        targets: list[SessionTarget] | None = None,
        target_summary: str | None = None,
        authorization_note: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: SessionStatus = SessionStatus.DRAFT,
    ) -> Session:
        resolved_mode = SessionMode(mode)
        resolved_persistence_mode = (
            SessionPersistenceMode(persistence_mode)
            if persistence_mode is not None
            else _default_persistence_mode(resolved_mode)
        )
        session = Session.create(
            title=title,
            goal=goal,
            mode=resolved_mode,
            persistence_mode=resolved_persistence_mode,
            workspace=workspace or str(self.settings.working_directory),
            status=SessionStatus(status),
            targets=list(targets or []),
            target_summary=target_summary,
            authorization_note=authorization_note,
            metadata=metadata,
        )
        self._prepare_session_for_persistence(session, touch=False)
        return self.repository.create(session)

    def get_session(self, identifier: str) -> Session | None:
        return self.repository.get(identifier)

    def require_session(self, identifier: str) -> Session:
        return self.repository.require(identifier)

    def list_sessions(
        self,
        *,
        mode: SessionMode | None = None,
        status: SessionStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Session]:
        return self.repository.list(
            mode=mode,
            status=status,
            title_query=title_query,
            limit=limit,
        )

    def get_latest_session(
        self,
        *,
        mode: SessionMode | None = None,
        status: SessionStatus | None = None,
        title_query: str | None = None,
    ) -> Session | None:
        sessions = self.list_sessions(
            mode=mode,
            status=status,
            title_query=title_query,
            limit=1,
        )
        if not sessions:
            return None
        return sessions[0]

    def save_session(self, session: Session) -> Session:
        existing = self.require_session(session.public_id or session.id)
        self._prepare_session_for_persistence(session, current_status=existing.status)
        return self.repository.update(session)

    def update_session_status(
        self,
        identifier: str,
        status: SessionStatus,
        *,
        last_error: str | None | object = _UNSET,
    ) -> Session:
        session = self.require_session(identifier)
        current_status = session.status
        session.status = SessionStatus(status)
        if last_error is not _UNSET:
            session.last_error = last_error
        self._prepare_session_for_persistence(session, current_status=current_status)
        return self.repository.update(session)

    def update_session_targets(
        self,
        identifier: str,
        *,
        targets: list[SessionTarget],
        target_summary: str | None = None,
    ) -> Session:
        session = self.require_session(identifier)
        session.targets = list(targets)
        session.target_summary = target_summary or Session.derive_target_summary(session.targets)
        self._prepare_session_for_persistence(session, current_status=session.status)
        return self.repository.update(session)

    def update_authorization_note(
        self,
        identifier: str,
        authorization_note: str | None,
    ) -> Session:
        session = self.require_session(identifier)
        session.authorization_note = authorization_note
        self._prepare_session_for_persistence(session, current_status=session.status)
        return self.repository.update(session)

    def _prepare_session_for_persistence(
        self,
        session: Session,
        *,
        current_status: SessionStatus | None = None,
        touch: bool = True,
    ) -> None:
        session.status = SessionStatus(session.status)
        if current_status is not None:
            Session.require_valid_transition(current_status, session.status)
        if session.target_summary is None:
            session.target_summary = Session.derive_target_summary(session.targets)
        if touch:
            session.updated_at = utc_now_iso()
        if session.status in TERMINAL_SESSION_STATUSES and session.closed_at is None:
            session.closed_at = session.updated_at
