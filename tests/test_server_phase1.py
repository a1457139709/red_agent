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
    assert payload["sequence"] == 1
    assert payload["project_id"] is None
    assert payload["session_id"] is None
    assert payload["task_id"] is None
    assert payload["payload"] == {"message": "connected", "channel": "events"}
