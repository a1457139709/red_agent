from __future__ import annotations

import json
from pathlib import Path

from agent.settings import Settings, get_settings
from models.control_center import Project, ProjectStatus
from storage.project_paths import project_manifest_path, project_reports_dir, project_root, project_sessions_dir
from storage.repositories.control_center import ProjectRepository
from storage.sqlite import SQLiteStorage

from .control_center_base import ControlCenterService


class ProjectService(ControlCenterService):
    def __init__(
        self,
        repository: ProjectRepository,
        settings: Settings,
    ) -> None:
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "settings", settings)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ProjectService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        return cls(ProjectRepository(storage), settings)

    def create_project(
        self,
        *,
        name: str,
        description: str | None = None,
    ) -> Project:
        project = Project.create(
            name=name,
            description=description,
            root_path=str(self.settings.projects_dir),
        )
        project.root_path = str(project_root(self.settings, project.id))
        project_sessions_dir(self.settings, project.id).mkdir(parents=True, exist_ok=True)
        project_reports_dir(self.settings, project.id).mkdir(parents=True, exist_ok=True)
        created = self.repository.create(project)
        self._prepare_project_manifest(created)
        return created

    def list_projects(
        self,
        *,
        status: ProjectStatus | None = None,
        limit: int | None = 50,
    ) -> list[Project]:
        return self.repository.list(status=status, limit=limit)

    def get_project(self, identifier: str) -> Project | None:
        return self.repository.get(identifier)

    def require_project(self, identifier: str) -> Project:
        return self.repository.require(identifier)

    def _prepare_project_manifest(self, project: Project) -> None:
        root = project_root(self.settings, project.id)
        manifest = project_manifest_path(self.settings, project.id)
        self._write_manifest(
            manifest,
            {
                "project_id": project.id,
                "public_id": project.public_id,
                "name": project.name,
                "description": project.description,
                "root_path": str(root),
                "created_at": project.created_at,
            },
        )

    def _write_manifest(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
