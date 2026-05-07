from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

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


def test_event_sequence_is_global_and_project_history_is_ordered(tmp_path):
    settings = build_settings(tmp_path)
    storage = SQLiteStorage(settings.sqlite_path)
    project = ProjectService.from_settings(settings).create_project(name="Ordering Lab")
    session_service = TargetSessionService.from_settings(settings)
    first_session = session_service.create_session(
        project_identifier=project.id,
        name="First target",
        target_value="10.10.10.10",
        target_type=TargetType.IP,
    )
    second_session = session_service.create_session(
        project_identifier=project.id,
        name="Second target",
        target_value="10.10.10.11",
        target_type=TargetType.IP,
    )

    first_event = EventRepository(storage).create(
        Event.create(
            project_id=project.id,
            session_id=first_session.id,
            event_kind="task.started",
            level="info",
            payload={"session": "first"},
        )
    )
    second_event = EventRepository(storage).create(
        Event.create(
            project_id=project.id,
            session_id=second_session.id,
            event_kind="task.completed",
            level="info",
            payload={"session": "second"},
        )
    )

    project_history = EventRepository(storage).list(project_id=project.id, limit=None)

    assert first_event.sequence == 1
    assert second_event.sequence == 2
    assert [item.id for item in project_history] == [second_event.id, first_event.id]


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


def test_session_dashboard_includes_workspace_sections(tmp_path):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="Web Lab")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Portal",
        target_value="portal.local",
        target_type=TargetType.HOST,
    )
    storage = SQLiteStorage(settings.sqlite_path)
    task = TaskRepository(storage).create(
        Task.create(
            project_id=project.id,
            session_id=session.id,
            task_type="port_scan",
            executor="nmap",
            result_json={
                "structured": {
                    "open_ports": [
                        {"port": 80, "protocol": "tcp", "service": "http"},
                        {"port": 443, "protocol": "tcp", "service": "https"},
                    ]
                }
            },
        )
    )
    TaskRepository(storage).create(
        Task.create(
            project_id=project.id,
            session_id=session.id,
            task_type="dir_scan",
            executor="ffuf",
            input_json={"base_url": "http://portal.local"},
            result_json={"structured": {"results": [{"status": 200, "url": "http://portal.local/admin"}]}},
        )
    )
    evidence = EvidenceRepository(storage).create(
        Evidence.create(
            project_id=project.id,
            session_id=session.id,
            source_task_id=task.id,
            evidence_type="service",
            title="HTTP reachable",
            summary="Landing page responds.",
        )
    )
    AttackPathNodeRepository(storage).create(
        AttackPathNode.create(
            project_id=project.id,
            session_id=session.id,
            stage="web-enum",
            title="Inspect admin login",
            status="open",
            next_action="Probe authentication and default creds.",
        )
    )
    CommandRunRepository(storage).create(
        CommandRun.create(
            project_id=project.id,
            session_id=session.id,
            terminal_id="term-1",
            command="curl -i http://portal.local/admin",
            exit_code=0,
            tags=["manual", "http"],
        )
    )
    FlagRepository(storage).create(
        Flag.create(
            project_id=project.id,
            session_id=session.id,
            flag_type="loot",
            value="admin:admin",
            source_evidence_id=evidence.id,
        )
    )

    dashboard = TargetSessionService.from_settings(settings).build_dashboard(session.public_id)

    assert {entry["url"] for entry in dashboard.web_entries} == {"http://portal.local", "https://portal.local"}
    assert dashboard.recent_commands[0]["command"] == "curl -i http://portal.local/admin"
    assert dashboard.next_actions[0]["next_action"] == "Probe authentication and default creds."
    assert dashboard.evidence[0]["title"] == "HTTP reachable"
    assert dashboard.flags[0]["value"] == "admin:admin"


def test_project_creation_rolls_back_when_manifest_write_fails(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    service = ProjectService.from_settings(settings)

    def fail_manifest(self, project):
        raise RuntimeError("manifest write failed")

    monkeypatch.setattr(ProjectService, "_prepare_project_manifest", fail_manifest)

    with pytest.raises(RuntimeError, match="manifest write failed"):
        service.create_project(name="Broken Project")

    assert service.list_projects(limit=None) == []
    if settings.projects_dir.exists():
        assert list(settings.projects_dir.iterdir()) == []


def test_session_creation_rolls_back_when_workspace_prep_fails(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="Rollback Lab")
    service = TargetSessionService.from_settings(settings)
    original = TargetSessionService._prepare_session_files

    def fail_prepare(self, project_arg, session_arg):
        original(self, project_arg, session_arg)
        raise RuntimeError("session prep failed")

    monkeypatch.setattr(TargetSessionService, "_prepare_session_files", fail_prepare)

    with pytest.raises(RuntimeError, match="session prep failed"):
        service.create_session(
            project_identifier=project.id,
            name="Broken session",
            target_value="10.10.10.12",
            target_type=TargetType.IP,
        )

    assert service.list_sessions(project_identifier=project.id, limit=None) == []
    session_roots = list(project_sessions_dir(settings, project.id).iterdir())
    assert session_roots == []


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


def test_event_websocket_replays_persisted_session_history(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    project = ProjectService.from_settings(settings).create_project(name="Replay Lab")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Replay target",
        target_value="10.10.10.15",
        target_type=TargetType.IP,
    )
    storage = SQLiteStorage(settings.sqlite_path)
    event = EventRepository(storage).create(
        Event.create(
            project_id=project.id,
            session_id=session.id,
            event_kind="task.completed",
            level="info",
            payload={"message": "scan finished"},
        )
    )

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr("server.ws.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/ws/events?session_id={session.public_id}&limit=10") as websocket:
            connected = websocket.receive_json()
            replayed = websocket.receive_json()

    assert replayed["event_id"] == event.id
    assert replayed["timestamp"] == event.created_at
    assert replayed["sequence"] == event.sequence
    assert replayed["event_kind"] == "task.completed"
    assert connected["event_kind"] == "connection.connected"
    assert connected["sequence"] == 0
    assert replayed["sequence"] > connected["sequence"]
