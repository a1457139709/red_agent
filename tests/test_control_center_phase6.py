from __future__ import annotations

import platform
import time

from fastapi.testclient import TestClient
import pytest

from agent.settings import Settings
from app.project_service import ProjectService
from app.target_session_service import TargetSessionService
from app.terminal_service import TerminalService
from models.control_center import CommandRun, TargetType
from server.app import create_app
from storage.repositories.control_center import (
    AttackPathEvidenceLinkRepository,
    AttackPathNodeRepository,
    CommandRunRepository,
    EventRepository,
)
from storage.sqlite import SQLiteStorage
from terminal.pty_manager import PtyManager


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def prepare_session(settings):
    project = ProjectService.from_settings(settings).create_project(name="Phase 6")
    session = TargetSessionService.from_settings(settings).create_session(
        project_identifier=project.id,
        name="Target",
        target_value="10.10.10.5",
        target_type=TargetType.IP,
    )
    return project, session


@pytest.mark.skipif(platform.system().lower().startswith("win"), reason="POSIX PTY only in Phase 6")
def test_pty_manager_can_start_stream_and_stop_process(tmp_path):
    output: list[str] = []
    exits: list[int | None] = []
    manager = PtyManager()

    terminal = manager.open(
        cwd=tmp_path,
        on_output=output.append,
        on_exit=exits.append,
    )
    manager.write(terminal.terminal_id, "echo phase6-pty\n")
    assert _wait_for(lambda: any("phase6-pty" in chunk for chunk in output))
    manager.close(terminal.terminal_id)
    assert _wait_for(lambda: exits != [])


@pytest.mark.skipif(platform.system().lower().startswith("win"), reason="POSIX PTY only in Phase 6")
def test_terminal_service_streams_output_persists_command_and_cleans_up(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    service = TerminalService.from_settings(settings)
    storage = SQLiteStorage(settings.sqlite_path)

    terminal = service.open_terminal(session_identifier=session.id)
    service.handle_input(terminal_id=terminal.terminal_id, data="echo phase6-service\n")

    assert _wait_for(
        lambda: any(
            event.event_kind == "terminal.output" and "phase6-service" in str(event.payload.get("chunk"))
            for event in EventRepository(storage).list(session_id=session.id, limit=None)
        )
    )
    service.close_terminal(terminal_id=terminal.terminal_id)
    assert _wait_for(
        lambda: any(
            command.ended_at is not None and command.output_ref
            for command in CommandRunRepository(storage).list(session_id=session.id, limit=None)
        )
    )
    command = CommandRunRepository(storage).list(session_id=session.id, limit=None)[0]
    assert command.command == "echo phase6-service"
    assert command.working_directory == terminal.working_directory
    assert command.output_summary is not None
    assert not service.pty_manager.has(terminal.terminal_id)


def test_command_output_can_be_saved_as_evidence(tmp_path):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    storage = SQLiteStorage(settings.sqlite_path)
    command = CommandRunRepository(storage).create(
        CommandRun.create(
            project_id=session.project_id,
            session_id=session.id,
            terminal_id="term-test",
            command="id",
            output_ref="artifacts/terminal/term-test/id.txt",
            output_summary="uid=1000",
            working_directory=str(tmp_path),
            started_at="2026-05-12T00:00:00+00:00",
            ended_at="2026-05-12T00:00:01+00:00",
        )
    )

    evidence = TerminalService.from_settings(settings).create_evidence_from_command(
        command_identifier=command.public_id,
        title="id output",
        selected_text="uid=1000(ctf)",
        tags=["manual", "terminal"],
    )

    assert evidence.evidence_type == "terminal_output"
    assert evidence.content_ref == command.output_ref
    assert evidence.payload["command_run_id"] == command.id
    assert evidence.payload["selected_text"] == "uid=1000(ctf)"
    assert CommandRunRepository(storage).get(command.id).tags == ["manual", "terminal"]
    node = AttackPathNodeRepository(storage).list(session_id=session.id, limit=None)[0]
    assert node.stage == "terminal-evidence"
    assert AttackPathEvidenceLinkRepository(storage).list_evidence_ids(node_id=node.id) == [evidence.id]


def test_phase6_terminal_api_routes(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)
    storage = SQLiteStorage(settings.sqlite_path)
    command = CommandRunRepository(storage).create(
        CommandRun.create(
            project_id=session.project_id,
            session_id=session.id,
            terminal_id="term-api",
            command="whoami",
            output_ref="artifacts/terminal/term-api/whoami.txt",
        )
    )

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        if not platform.system().lower().startswith("win"):
            opened = client.post(f"/api/sessions/{session.public_id}/terminals", json={"rows": 20, "cols": 100})
            assert opened.status_code == 201
            assert opened.json()["terminal"]["session_id"] == session.id

        commands = client.get("/api/terminals/term-api/commands")
        assert commands.status_code == 200
        assert commands.json()["commands"][0]["command"] == "whoami"

        evidence = client.post(
            f"/api/commands/{command.public_id}/evidence",
            json={"title": "whoami output", "selected_text": "ctf-user"},
        )
        assert evidence.status_code == 201
        assert evidence.json()["evidence"]["evidence_type"] == "terminal_output"


@pytest.mark.skipif(platform.system().lower().startswith("win"), reason="POSIX PTY only in Phase 6")
def test_terminal_websocket_open_input_resize_and_close(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    _project, session = prepare_session(settings)

    monkeypatch.setattr("server.lifecycle.get_settings", lambda: settings)
    monkeypatch.setattr("server.ws.get_settings", lambda: settings)

    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/ws/events?session_id={session.id}&replay=false") as websocket:
            connected = websocket.receive_json()
            assert connected["event_kind"] == "connection.connected"

            websocket.send_json(
                {
                    "event_kind": "terminal.open",
                    "payload": {"session_id": session.id, "rows": 20, "cols": 100},
                }
            )
            opened = _receive_until(websocket, lambda event: event["event_kind"] == "terminal.opened")
            terminal_id = opened["payload"]["terminal_id"]

            websocket.send_json(
                {
                    "event_kind": "terminal.resize",
                    "payload": {"terminal_id": terminal_id, "rows": 22, "cols": 120},
                }
            )
            websocket.send_json(
                {
                    "event_kind": "terminal.input",
                    "payload": {"terminal_id": terminal_id, "data": "echo phase6-ws\n"},
                }
            )
            output = _receive_until(
                websocket,
                lambda event: (
                    event["event_kind"] == "terminal.output"
                    and "phase6-ws" in str(event["payload"].get("chunk"))
                ),
            )
            assert output["payload"]["terminal_id"] == terminal_id

            websocket.send_json({"event_kind": "terminal.close", "payload": {"terminal_id": terminal_id}})
            exited = _receive_until(websocket, lambda event: event["event_kind"] == "terminal.exited")
            assert exited["payload"]["terminal_id"] == terminal_id


def _receive_until(websocket, predicate, *, max_messages: int = 30):
    for _ in range(max_messages):
        event = websocket.receive_json()
        if predicate(event):
            return event
    raise AssertionError("Expected WebSocket event was not received.")


def _wait_for(predicate, *, timeout_seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False
