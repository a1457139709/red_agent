from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from agent.settings import Settings
from app.project_service import ProjectService
from app.scanner_service import ScannerService
from app.target_session_service import TargetSessionService
from models.control_center import TargetType
from runtime.scanner_tasks import ScannerTaskRuntime
from server.app import create_app
from storage.repositories.control_center import EventRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def write_auth_config(settings, *, enabled=True):
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "control-center-auth.json").write_text(
        json.dumps({"enabled": enabled, "username": "admin", "password": "change-me"}),
        encoding="utf-8",
    )


def prepare_session(settings):
    project = ProjectService.from_settings(settings).create_project(name="Phase 8")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
    )
    return project, session


def test_phase8_auth_config_missing_keeps_local_api_unprotected(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        session = client.get("/api/auth/session")
        projects = client.get("/api/projects")

    assert session.status_code == 200
    assert session.json()["auth"] == {"enabled": False, "authenticated": True, "username": None}
    assert projects.status_code == 200


def test_phase8_enabled_auth_requires_bearer_token(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    write_auth_config(settings)
    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/projects").status_code == 401
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401

        login = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
        assert login.status_code == 200
        token = login.json()["token"]
        assert token

        authorized = client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
        assert authorized.status_code == 200


def test_phase8_websocket_auth_uses_query_token(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    write_auth_config(settings)
    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/events") as websocket:
            denied = websocket.receive_json()
        assert denied["event_kind"] == "error"
        assert denied["payload"]["code"] == "authentication_required"

        login = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
        token = login.json()["token"]
        with client.websocket_connect(f"/ws/events?auth_token={token}&replay=false") as websocket:
            connected = websocket.receive_json()
        assert connected["event_kind"] == "connection.connected"


def test_phase8_scanner_runtime_can_cancel_pending_future(tmp_path):
    settings = build_settings(tmp_path)
    runtime = ScannerTaskRuntime(settings=settings, max_workers=1)

    def slow_execute(_task_identifier):
        time.sleep(0.2)

    runtime._execute = slow_execute  # type: ignore[method-assign]
    try:
        runtime.submit("running-task")
        runtime.submit("pending-task")
        assert runtime.cancel_pending("pending-task") is True
        assert runtime.cancel_pending("running-task") is False
    finally:
        runtime.shutdown()


def test_phase8_cancelled_task_records_event_and_tool_config_validation(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = ScannerService.from_settings(settings)
    task = service.enqueue_scan_task(
        session_identifier=session.id,
        task_type="port_scan",
        input_data={"target_host": "10.10.10.5"},
    )

    cancelled = service.cancel_task(task.id)
    events = EventRepository(SQLiteStorage(settings.sqlite_path)).list(session_id=session.id, limit=10)

    assert cancelled.status.value == "cancelled"
    assert any(event.event_kind == "task.cancelled" for event in events)

    config = service.update_config(
        {
            "tools": {
                "nmap": {"binary_path": "/opt/nmap", "timeout_seconds": 60, "extra_args": ["-Pn"]},
                "ffuf": {"default_wordlist": "/tmp/words.txt"},
                "nuclei": {"templates_path": "/tmp/nuclei-templates"},
            }
        }
    )
    assert config.for_tool("nmap").timeout_seconds == 60
    assert config.for_tool("ffuf").default_wordlist == "/tmp/words.txt"
    assert config.for_tool("nuclei").templates_path == "/tmp/nuclei-templates"


def test_phase8_tool_config_route_rejects_invalid_timeout(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        response = client.patch("/api/tools/config", json={"tools": {"nmap": {"timeout_seconds": 0}}})

    assert response.status_code == 400
