from __future__ import annotations

from pathlib import Path
import os

from agent.settings import Settings


def project_root(settings: Settings, project_id: str) -> Path:
    return settings.projects_dir / _validate_path_segment(project_id, field_name="project_id")


def project_manifest_path(settings: Settings, project_id: str) -> Path:
    return project_root(settings, project_id) / "project.json"


def project_sessions_dir(settings: Settings, project_id: str) -> Path:
    return project_root(settings, project_id) / "sessions"


def project_reports_dir(settings: Settings, project_id: str) -> Path:
    return project_root(settings, project_id) / "reports"


def project_session_root(
    settings: Settings,
    *,
    project_id: str,
    session_id: str,
) -> Path:
    return project_sessions_dir(settings, project_id) / _validate_path_segment(
        session_id,
        field_name="session_id",
    )


def project_session_artifacts_dir(
    settings: Settings,
    *,
    project_id: str,
    session_id: str,
) -> Path:
    return project_session_root(settings, project_id=project_id, session_id=session_id) / "artifacts"


def project_session_reports_dir(
    settings: Settings,
    *,
    project_id: str,
    session_id: str,
) -> Path:
    return project_session_root(settings, project_id=project_id, session_id=session_id) / "reports"


def project_session_scripts_dir(
    settings: Settings,
    *,
    project_id: str,
    session_id: str,
) -> Path:
    return project_session_root(settings, project_id=project_id, session_id=session_id) / "scripts"


def project_session_notes_dir(
    settings: Settings,
    *,
    project_id: str,
    session_id: str,
) -> Path:
    return project_session_root(settings, project_id=project_id, session_id=session_id) / "notes"


def resolve_project_relative_path(
    settings: Settings,
    *,
    project_id: str,
    relative_path: str,
) -> Path:
    root = project_root(settings, project_id).resolve()
    return _resolve_under_root(root, relative_path, owner=f"project:{project_id}")


def resolve_project_session_relative_path(
    settings: Settings,
    *,
    project_id: str,
    session_id: str,
    relative_path: str,
) -> Path:
    root = project_session_root(
        settings,
        project_id=project_id,
        session_id=session_id,
    ).resolve()
    return _resolve_under_root(root, relative_path, owner=f"project-session:{project_id}:{session_id}")


def _resolve_under_root(root: Path, relative_path: str, *, owner: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError(f"Path for {owner} must be relative: {relative_path}")
    resolved = (root / candidate).resolve()
    if os.path.commonpath([str(resolved), str(root)]) != str(root):
        raise ValueError(f"Path for {owner} escapes its directory: {relative_path}")
    return resolved


def _validate_path_segment(value: str, *, field_name: str) -> str:
    segment = value.strip()
    if not segment:
        raise ValueError(f"{field_name} must be non-empty.")
    if segment in {".", ".."} or "/" in segment or "\\" in segment:
        raise ValueError(f"{field_name} must be a single path segment.")
    if Path(segment).name != segment:
        raise ValueError(f"{field_name} must be a single path segment.")
    return segment
