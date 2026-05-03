from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings, get_settings
from models.control_center import Project, SessionDashboard, TargetSession, TargetSessionStatus, TargetType
from storage.project_paths import (
    project_session_artifacts_dir,
    project_session_notes_dir,
    project_session_reports_dir,
    project_session_root,
    project_session_scripts_dir,
)
from storage.repositories.control_center import ProjectRepository, TargetSessionRepository
from storage.sqlite import SQLiteStorage

from .control_center_base import ControlCenterService


@dataclass(frozen=True, slots=True)
class TargetSessionBundle:
    project: Project
    session: TargetSession


class TargetSessionService(ControlCenterService):
    def __init__(
        self,
        repository: TargetSessionRepository,
        project_repository: ProjectRepository,
        settings: Settings,
    ) -> None:
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "project_repository", project_repository)
        object.__setattr__(self, "settings", settings)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "TargetSessionService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(
            TargetSessionRepository(storage),
            ProjectRepository(storage),
            settings,
        )

    def create_session(
        self,
        *,
        project_identifier: str,
        name: str,
        target_value: str,
        target_type: TargetType,
        summary: str | None = None,
    ) -> TargetSession:
        project = self.project_repository.require(project_identifier)
        session = TargetSession.create(
            project_id=project.id,
            name=name,
            target_value=target_value,
            target_type=TargetType(target_type),
            summary=summary,
        )
        self._prepare_session_files(project, session)
        return self.repository.create(session)

    def list_sessions(
        self,
        *,
        project_identifier: str,
        status: TargetSessionStatus | None = None,
        limit: int | None = 50,
    ) -> list[TargetSession]:
        project = self.project_repository.require(project_identifier)
        return self.repository.list(project_id=project.id, status=status, limit=limit)

    def get_session(self, identifier: str) -> TargetSession | None:
        return self.repository.get(identifier)

    def require_session(self, identifier: str) -> TargetSession:
        return self.repository.require(identifier)

    def build_dashboard(self, session_identifier: str) -> SessionDashboard:
        session = self.require_session(session_identifier)
        project = self.project_repository.require(session.project_id)
        return SessionDashboard(project=project, session=session)

    def get_bundle(self, session_identifier: str) -> TargetSessionBundle:
        session = self.require_session(session_identifier)
        project = self.project_repository.require(session.project_id)
        return TargetSessionBundle(project=project, session=session)

    def _prepare_session_files(self, project: Project, session: TargetSession) -> None:
        project_session_root(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        ).mkdir(parents=True, exist_ok=True)
        project_session_artifacts_dir(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        ).mkdir(parents=True, exist_ok=True)
        project_session_reports_dir(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        ).mkdir(parents=True, exist_ok=True)
        project_session_scripts_dir(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        ).mkdir(parents=True, exist_ok=True)
        project_session_notes_dir(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        ).mkdir(parents=True, exist_ok=True)


def build_target_session_service(settings: Settings | None = None) -> TargetSessionService:
    return TargetSessionService.from_settings(settings)
