from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from agent.settings import Settings, get_settings
from models.control_center import Project, SessionDashboard, TargetSession, TargetSessionStatus, TargetType
from storage.project_paths import (
    project_session_artifacts_dir,
    project_session_root,
    project_session_notes_dir,
    project_session_reports_dir,
    project_session_scripts_dir,
)
from storage.repositories.control_center import ProjectRepository, TargetSessionRepository
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    CommandRunRepository,
    EvidenceRepository,
    FlagRepository,
    TaskRepository,
)
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
        session_root = project_session_root(
            self.settings,
            project_id=project.id,
            session_id=session.id,
        )
        storage = SQLiteStorage(self.settings.sqlite_path)
        with storage.connect() as connection:
            try:
                self.repository.create_in_connection(connection, session)
                self._prepare_session_files(project, session)
            except Exception:
                connection.rollback()
                self._cleanup_path(session_root)
                raise
            connection.commit()
        return session

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
        storage = SQLiteStorage(self.settings.sqlite_path)
        tasks = TaskRepository(storage).list(session_id=session.id, limit=None)
        evidence = EvidenceRepository(storage).list(session_id=session.id, limit=None)
        attack_path = AttackPathNodeRepository(storage).list(session_id=session.id, limit=None)
        commands = CommandRunRepository(storage).list(session_id=session.id, limit=10)
        flags = FlagRepository(storage).list(session_id=session.id, limit=None)
        open_ports = _collect_scan_items(tasks, "open_ports")
        directory_findings = _collect_scan_items(tasks, "results")
        poc_hits = _collect_scan_items(tasks, "matches")
        return SessionDashboard(
            project=project,
            session=session,
            task_counts=_count_by_status(tasks),
            evidence_count=len(evidence),
            flag_count=len(flags),
            open_ports=open_ports,
            web_entries=_collect_web_entries(
                session=session,
                tasks=tasks,
                open_ports=open_ports,
            ),
            directory_findings=directory_findings,
            poc_hits=poc_hits,
            attack_path=[node.to_row() for node in attack_path],
            recent_commands=[command.to_row() for command in commands],
            evidence=[item.to_row() for item in evidence],
            flags=[item.to_row() for item in flags],
            next_actions=[_serialize_next_action(node) for node in attack_path if node.next_action],
        )

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

    def _cleanup_path(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def build_target_session_service(settings: Settings | None = None) -> TargetSessionService:
    return TargetSessionService.from_settings(settings)


def _count_by_status(tasks) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.status.value] = counts.get(task.status.value, 0) + 1
    return counts


def _collect_scan_items(tasks, key: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for task in tasks:
        structured = task.result_json.get("structured")
        if not isinstance(structured, dict):
            continue
        value = structured.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _collect_web_entries(
    *,
    session: TargetSession,
    tasks,
    open_ports: list[dict[str, object]],
) -> list[dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for url, source in _iter_session_web_urls(session=session, tasks=tasks, open_ports=open_ports):
        if url in entries:
            continue
        parsed = urlsplit(url)
        entries[url] = {
            "url": url,
            "scheme": parsed.scheme,
            "host": parsed.hostname or "",
            "port": parsed.port or _default_port_for_scheme(parsed.scheme),
            "source": source,
        }
    return list(entries.values())


def _iter_session_web_urls(*, session: TargetSession, tasks, open_ports: list[dict[str, object]]):
    if session.target_type == TargetType.URL:
        yield session.target_value, "session.target"
    for task in tasks:
        input_data = task.input_json
        if task.task_type == "dir_scan":
            base_url = input_data.get("base_url") or input_data.get("target")
            if isinstance(base_url, str) and base_url.strip():
                yield base_url.strip(), "dir_scan"
        if task.task_type == "poc_scan":
            target_url = input_data.get("target_url") or input_data.get("target")
            if isinstance(target_url, str) and target_url.strip():
                yield target_url.strip(), "poc_scan"
    if session.target_type == TargetType.URL:
        return
    host = session.target_value.strip()
    for port in open_ports:
        url = _infer_web_url(host=host, port_data=port)
        if url is not None:
            yield url, "port_scan"


def _infer_web_url(*, host: str, port_data: dict[str, object]) -> str | None:
    port = port_data.get("port")
    if not isinstance(port, int):
        return None
    service = str(port_data.get("service") or "").lower()
    scheme: str | None = None
    if "https" in service or port in {443, 8443, 9443}:
        scheme = "https"
    elif "http" in service or port in {80, 8000, 8080, 8888}:
        scheme = "http"
    if scheme is None:
        return None
    default_port = _default_port_for_scheme(scheme)
    netloc = host if port == default_port else f"{host}:{port}"
    return f"{scheme}://{netloc}"


def _default_port_for_scheme(scheme: str) -> int | None:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None


def _serialize_next_action(node) -> dict[str, object]:
    return {
        "id": node.id,
        "public_id": node.public_id,
        "stage": node.stage,
        "title": node.title,
        "status": node.status,
        "source_ref": node.source_ref,
        "next_action": node.next_action,
        "created_at": node.created_at,
    }
