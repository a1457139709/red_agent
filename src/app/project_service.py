from __future__ import annotations

import json
from pathlib import Path
import shutil

from agent.settings import Settings, get_settings
from models.control_center import Project, ProjectDashboard, ProjectStatus, TargetSessionStatus
from models.run import utc_now_iso
from storage.project_paths import project_manifest_path, project_reports_dir, project_root, project_sessions_dir
from storage.repositories.control_center import (
    EventRepository,
    FindingRepository,
    FlagRepository,
    ProjectRepository,
    TargetSessionRepository,
    TaskRepository,
)
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
        root = project_root(self.settings, project.id)
        project.root_path = str(root)
        sessions_dir = project_sessions_dir(self.settings, project.id)
        reports_dir = project_reports_dir(self.settings, project.id)
        storage = SQLiteStorage(self.settings.sqlite_path)
        with storage.connect() as connection:
            try:
                self.repository.create_in_connection(connection, project)
                sessions_dir.mkdir(parents=True, exist_ok=True)
                reports_dir.mkdir(parents=True, exist_ok=True)
                self._prepare_project_manifest(project)
            except Exception:
                connection.rollback()
                self._cleanup_path(root)
                raise
            connection.commit()
        return project

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

    def update_project(
        self,
        identifier: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
    ) -> Project:
        project = self.require_project(identifier)
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if status is not None:
            project.status = ProjectStatus(status)
        project.updated_at = utc_now_iso()

        storage = SQLiteStorage(self.settings.sqlite_path)
        session_repository = TargetSessionRepository(storage)
        sessions = session_repository.list(project_id=project.id, limit=None) if project.status == ProjectStatus.ARCHIVED else []
        with storage.connect() as connection:
            try:
                self.repository.update_in_connection(connection, project)
                if project.status == ProjectStatus.ARCHIVED:
                    for session in sessions:
                        if session.status == TargetSessionStatus.ARCHIVED:
                            continue
                        session.status = TargetSessionStatus.ARCHIVED
                        session.updated_at = project.updated_at
                        session_repository.update_in_connection(connection, session)
                self._prepare_project_manifest(project)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return project

    def build_dashboard(self, identifier: str, *, activity_limit: int = 20) -> ProjectDashboard:
        project = self.require_project(identifier)
        storage = SQLiteStorage(self.settings.sqlite_path)
        session_repository = TargetSessionRepository(storage)
        task_repository = TaskRepository(storage)
        finding_repository = FindingRepository(storage)
        flag_repository = FlagRepository(storage)
        event_repository = EventRepository(storage)

        sessions = session_repository.list(project_id=project.id, limit=None)
        tasks = task_repository.list_by_project(project_id=project.id, limit=None)
        findings = finding_repository.list_by_project(project_id=project.id, limit=None)
        flags = flag_repository.list_by_project(project_id=project.id, limit=None)
        activity = event_repository.list(project_id=project.id, limit=activity_limit)
        session_public_ids = {session.id: session.public_id for session in sessions}

        return ProjectDashboard(
            project=project,
            sessions=sessions,
            session_counts=_count_session_statuses(sessions),
            task_counts=_count_task_statuses(tasks),
            finding_counts=_count_findings_by_severity(findings),
            running_task_count=sum(1 for task in tasks if task.status.value == "running"),
            open_service_count=len(_collect_open_services(tasks)),
            finding_count=len(findings),
            flag_count=len(flags),
            recent_activity=[
                {
                    "event_id": event.id,
                    "project_id": event.project_id,
                    "session_id": event.session_id,
                    "session_public_id": session_public_ids.get(event.session_id or ""),
                    "task_id": event.task_id,
                    "event_kind": event.event_kind,
                    "level": event.level,
                    "payload": dict(event.payload),
                    "sequence": event.sequence,
                    "created_at": event.created_at,
                }
                for event in activity
            ],
        )

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
                "status": project.status.value,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
            },
        )

    def _write_manifest(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cleanup_path(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _count_session_statuses(sessions) -> dict[str, int]:
    counts: dict[str, int] = {}
    for session in sessions:
        counts[session.status.value] = counts.get(session.status.value, 0) + 1
    return counts


def _count_task_statuses(tasks) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.status.value] = counts.get(task.status.value, 0) + 1
    return counts


def _count_findings_by_severity(findings) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def _collect_open_services(tasks) -> set[tuple[str, object, object]]:
    services: set[tuple[str, object, object]] = set()
    for task in tasks:
        structured = task.result_json.get("structured")
        if not isinstance(structured, dict):
            continue
        open_ports = structured.get("open_ports")
        if not isinstance(open_ports, list):
            continue
        for item in open_ports:
            if not isinstance(item, dict):
                continue
            services.add(
                (
                    str(item.get("host") or task.input_json.get("target_host") or task.input_json.get("target") or ""),
                    item.get("port"),
                    item.get("protocol"),
                )
            )
    return services
