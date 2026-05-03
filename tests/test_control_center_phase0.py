from __future__ import annotations

import pytest

from agent.settings import Settings
from app import (
    AttackPathService,
    ProjectService,
    ScannerService,
    TargetSessionService,
    TerminalService,
    WriteupService,
)
from storage.project_paths import (
    project_manifest_path,
    project_reports_dir,
    project_root,
    project_session_artifacts_dir,
    project_session_notes_dir,
    project_session_reports_dir,
    project_session_root,
    project_session_scripts_dir,
    resolve_project_relative_path,
    resolve_project_session_relative_path,
)


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_control_center_services_are_importable_and_constructible(tmp_path):
    settings = build_settings(tmp_path)

    services = [
        ProjectService.from_settings(settings),
        TargetSessionService.from_settings(settings),
        AttackPathService.from_settings(settings),
        ScannerService.from_settings(settings),
        TerminalService.from_settings(settings),
        WriteupService.from_settings(settings),
    ]

    assert [service.settings for service in services] == [settings] * len(services)


def test_projects_dir_uses_red_code_projects_root(tmp_path):
    settings = build_settings(tmp_path)

    assert settings.projects_dir == tmp_path / ".red-code" / "projects"


def test_project_path_helpers_define_phase0_layout(tmp_path):
    settings = build_settings(tmp_path)

    assert project_root(settings, "project-1") == tmp_path / ".red-code" / "projects" / "project-1"
    assert project_manifest_path(settings, "project-1") == project_root(settings, "project-1") / "project.json"
    assert project_reports_dir(settings, "project-1") == project_root(settings, "project-1") / "reports"
    assert project_session_root(
        settings,
        project_id="project-1",
        session_id="session-1",
    ) == project_root(settings, "project-1") / "sessions" / "session-1"
    assert project_session_artifacts_dir(
        settings,
        project_id="project-1",
        session_id="session-1",
    ) == project_session_root(settings, project_id="project-1", session_id="session-1") / "artifacts"
    assert project_session_reports_dir(
        settings,
        project_id="project-1",
        session_id="session-1",
    ) == project_session_root(settings, project_id="project-1", session_id="session-1") / "reports"
    assert project_session_scripts_dir(
        settings,
        project_id="project-1",
        session_id="session-1",
    ) == project_session_root(settings, project_id="project-1", session_id="session-1") / "scripts"
    assert project_session_notes_dir(
        settings,
        project_id="project-1",
        session_id="session-1",
    ) == project_session_root(settings, project_id="project-1", session_id="session-1") / "notes"


def test_project_path_resolvers_reject_directory_escape(tmp_path):
    settings = build_settings(tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        resolve_project_relative_path(
            settings,
            project_id="project-1",
            relative_path="../agent.db",
        )

    with pytest.raises(ValueError, match="escapes"):
        resolve_project_session_relative_path(
            settings,
            project_id="project-1",
            session_id="session-1",
            relative_path="../project.json",
        )


def test_project_path_helpers_reject_non_segment_ids(tmp_path):
    settings = build_settings(tmp_path)

    with pytest.raises(ValueError, match="single path segment"):
        project_root(settings, "../project-1")

    with pytest.raises(ValueError, match="single path segment"):
        project_session_root(settings, project_id="project-1", session_id="nested/session")
