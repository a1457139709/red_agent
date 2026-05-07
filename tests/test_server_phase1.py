from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import create_app


def test_app_factory_imports_without_side_effects():
    app = create_app()

    assert app.title == "red-code Control Center"


def test_health_endpoint_returns_ok():
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "control-center"
    assert payload["started_at"]


def test_event_websocket_emits_connected_envelope():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/events") as websocket:
            payload = websocket.receive_json()

    assert payload["event_kind"] == "connection.connected"
    assert payload["sequence"] == 0
    assert payload["project_id"] is None
    assert payload["session_id"] is None
    assert payload["task_id"] is None
    assert payload["payload"] == {"message": "connected", "channel": "events"}


def test_event_websocket_rejects_non_object_messages_without_traceback():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/events") as websocket:
            websocket.receive_json()
            websocket.send_json(["not", "an", "object"])
            payload = websocket.receive_json()

    assert payload["event_kind"] == "error"
    assert payload["sequence"] == 1
    assert payload["payload"]["code"] == "invalid_message"


def test_event_websocket_sequence_only_counts_sent_events():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/events") as websocket:
            connected = websocket.receive_json()
            websocket.send_json({"event_kind": "unknown"})
            error = websocket.receive_json()
            websocket.send_json({"event_kind": "ping"})
            pong = websocket.receive_json()

    assert connected["sequence"] == 0
    assert error["sequence"] == 1
    assert error["event_kind"] == "error"
    assert pong["sequence"] == 2
    assert pong["event_kind"] == "connection.pong"
