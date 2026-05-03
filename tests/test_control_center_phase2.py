from __future__ import annotations

from fastapi.testclient import TestClient

from agent.settings import Settings
from app.project_service import ProjectService
from app.target_session_service import TargetSessionService
from models.control_center import AttackPathNode, CommandRun, Event, Evidence, Flag, TargetType, Task
from server.app import create_app
from storage.project_paths import (
    project_manifest_path,
    project_reports_dir,
    project_session_artifacts_dir,
    project_session_notes_dir,
    project_session_reports_dir,
    project_session_root,
    project_session_scripts_dir,
    project_sessions_dir,
)
from storage.repositories.control_center import (
    AttackPathNodeRepository,
    CommandRunRepository,
    ControlCenterSchemaRepository,
    EventRepository,
    EvidenceRepository,
    FlagRepository,
    ProjectRepository,
    TargetSessionRepository,
    TaskRepository,
)
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_project_repository_creates_lists_and_gets_projects(tmp_path):
    settings = build_settings(tmp_path)
    service = ProjectService.from_settings(settings)

    project = service.create_project(name="HTB Lab", description="Practice targets")

    loaded = service.require_project(project.public_id)
    projects = service.list_projects(limit=None)
    assert project.public_id == "P0001"
    assert loaded.id == project.id
    assert [item.id for item in projects] == [project.id]


def test_target_session_repository_creates_lists_and_gets_sessions(tmp_path):
    settings = build_settings(tmp_path)
    project_service = ProjectService.from_settings(settings)
    session_service = TargetSessionService.from_settings(settings)
    project = project_service.create_project(name="HTB Lab")
    other_project = project_service.create_project(name="Other Lab")

    session = session_service.create_session(
        project_identifier=project.public_id,
        name="Linux target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
    )
    session_service.create_session(
        project_identifier=other_project.public_id,
        name="Other target",
        target_value="example.test",
        target_type=TargetType.DOMAIN,
    )

    assert session.public_id == "T0001"
    assert session_service.require_session(session.public_id).id == session.id
    assert [item.id for item in session_service.list_sessions(project_identifier=project.public_id)] == [session.id]


def test_project_and_session_filesystem_layout_is_created(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="VulnHub")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Web target",
        target_value="https://target.local",
        target_type=TargetType.URL,
    )

    assert project_manifest_path(settings, project.id).exists()
    assert project_sessions_dir(settings, project.id).is_dir()
    assert project_reports_dir(settings, project.id).is_dir()
    assert project_session_root(settings, project_id=project.id, session_id=session.id).is_dir()
    assert project_session_artifacts_dir(settings, project_id=project.id, session_id=session.id).is_dir()
    assert project_session_reports_dir(settings, project_id=project.id, session_id=session.id).is_dir()
    assert project_session_scripts_dir(settings, project_id=project.id, session_id=session.id).is_dir()
    assert project_session_notes_dir(settings, project_id=project.id, session_id=session.id).is_dir()


def test_control_center_schema_initializes_reserved_tables(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    ControlCenterSchemaRepository(storage)

    expected_tables = {
        "ctf_projects",
        "ctf_target_sessions",
        "ctf_tasks",
        "ctf_events",
        "ctf_evidence",
        "ctf_attack_path_nodes",
        "ctf_command_runs",
        "ctf_flags",
    }
    with storage.connect() as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    assert expected_tables.issubset({row["name"] for row in rows})


def test_phase2_supporting_repositories_persist_session_entities(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    project = ProjectService.from_settings(settings).create_project(name="Persistence Lab")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.8",
        target_type=TargetType.IP,
    )

    task = TaskRepository(storage).create(
        Task.create(
            project_id=project.id,
            session_id=session.id,
            task_type="port_scan",
            executor="scanner",
            input_json={"target": session.target_value},
        )
    )
    event = EventRepository(storage).create(
        Event.create(
            project_id=project.id,
            session_id=session.id,
            task_id=task.id,
            event_kind="task.created",
            level="info",
            payload={"task_id": task.id},
        )
    )
    evidence = EvidenceRepository(storage).create(
        Evidence.create(
            project_id=project.id,
            session_id=session.id,
            source_task_id=task.id,
            evidence_type="service",
            title="Open SSH",
            payload={"port": 22},
        )
    )
    node = AttackPathNodeRepository(storage).create(
        AttackPathNode.create(
            project_id=project.id,
            session_id=session.id,
            stage="enumeration",
            title="Review SSH banner",
            status="open",
        )
    )
    command = CommandRunRepository(storage).create(
        CommandRun.create(
            project_id=project.id,
            session_id=session.id,
            terminal_id="term-1",
            command="nmap -sV 10.10.10.8",
            tags=["scan"],
        )
    )
    flag = FlagRepository(storage).create(
        Flag.create(
            project_id=project.id,
            session_id=session.id,
            flag_type="user",
            value="flag{example}",
            source_evidence_id=evidence.id,
        )
    )

    assert TaskRepository(storage).get(task.public_id).id == task.id
    assert EventRepository(storage).get(event.id).sequence == 1
    assert [item.id for item in EvidenceRepository(storage).list(session_id=session.id)] == [evidence.id]
    assert [item.id for item in AttackPathNodeRepository(storage).list(session_id=session.id)] == [node.id]
    assert [item.id for item in CommandRunRepository(storage).list(session_id=session.id)] == [command.id]
    assert [item.id for item in FlagRepository(storage).list(session_id=session.id)] == [flag.id]


def test_session_dashboard_empty_state(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="Local Lab")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Initial target",
        target_value="target.local",
        target_type=TargetType.HOST,
    )

    dashboard = TargetSessionService.from_settings(settings).build_dashboard(session.public_id)

    assert dashboard.project.id == project.id
    assert dashboard.session.id == session.id
    assert dashboard.open_ports == []
    assert dashboard.attack_path == []
    assert dashboard.task_counts == {}
    assert dashboard.evidence_count == 0
    assert dashboard.flag_count == 0


def test_phase2_project_and_session_api_routes(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr("app.project_service.get_settings", lambda: settings)
    monkeypatch.setattr("app.target_session_service.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        create_project = client.post(
            "/api/projects",
            json={"name": "HTB Lab", "description": "Practice"},
        )
        assert create_project.status_code == 201
        project = create_project.json()["project"]

        list_projects = client.get("/api/projects")
        assert list_projects.status_code == 200
        assert [item["id"] for item in list_projects.json()["projects"]] == [project["id"]]

        get_project = client.get(f"/api/projects/{project['public_id']}")
        assert get_project.status_code == 200
        assert get_project.json()["project"]["id"] == project["id"]

        create_session = client.post(
            f"/api/projects/{project['public_id']}/sessions",
            json={
                "name": "Linux target",
                "target_value": "10.10.10.5",
                "target_type": "ip",
            },
        )
        assert create_session.status_code == 201
        session = create_session.json()["session"]

        list_sessions = client.get(f"/api/projects/{project['id']}/sessions")
        assert list_sessions.status_code == 200
        assert [item["id"] for item in list_sessions.json()["sessions"]] == [session["id"]]

        get_session = client.get(f"/api/sessions/{session['public_id']}")
        assert get_session.status_code == 200
        assert get_session.json()["session"]["target_value"] == "10.10.10.5"

        dashboard = client.get(f"/api/sessions/{session['id']}/dashboard")
        assert dashboard.status_code == 200
        payload = dashboard.json()["dashboard"]
        assert payload["target"] == {"value": "10.10.10.5", "type": "ip", "summary": None}
        assert payload["open_ports"] == []
        assert payload["attack_path"] == []
        assert payload["next_actions"] == []
