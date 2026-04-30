from runtime.execution_events import (
    ExecutionEventType,
    ExecutionOutcome,
    ExecutionProgressEvent,
)


def test_execution_progress_event_to_dict_includes_required_fields():
    event = ExecutionProgressEvent(
        event_type=ExecutionEventType.STEP_STARTED,
        session_id="session-1",
        session_public_id="S0001",
        step_type="tool",
        step_label="http_probe",
        target_summary="example.com",
        message="running",
        timestamp="2026-04-09T10:00:00+00:00",
    )

    payload = event.to_dict()

    assert payload == {
        "event_type": "step_started",
        "session_id": "session-1",
        "session_public_id": "S0001",
        "step_type": "tool",
        "step_label": "http_probe",
        "target_summary": "example.com",
        "message": "running",
        "action_name": None,
        "risk_level": None,
        "reason": None,
        "payload": {},
        "timestamp": "2026-04-09T10:00:00+00:00",
    }


def test_execution_progress_event_supports_confirmation_fields():
    event = ExecutionProgressEvent(
        event_type=ExecutionEventType.CONFIRMATION_REQUIRED,
        session_id="session-1",
        session_public_id="S0001",
        action_name="poc_execute",
        risk_level="dangerous",
        reason="requires explicit approval",
    )

    payload = event.to_dict()

    assert payload["event_type"] == "confirmation_required"
    assert payload["action_name"] == "poc_execute"
    assert payload["risk_level"] == "dangerous"
    assert payload["reason"] == "requires explicit approval"


def test_execution_progress_event_serializes_structured_payload():
    event = ExecutionProgressEvent(
        event_type=ExecutionEventType.STEP_COMPLETED,
        session_id="session-1",
        session_public_id="S0001",
        step_type="tool",
        step_label="port_scan",
        payload={"tool_event": {"tool_name": "port_scan", "output": {"open_ports": []}}},
    )

    payload = event.to_dict()

    assert payload["payload"]["tool_event"]["tool_name"] == "port_scan"
    assert payload["payload"]["tool_event"]["output"] == {"open_ports": []}


def test_execution_outcome_is_completed_only_for_success():
    completed = ExecutionOutcome(status="completed", response="ok")
    failed = ExecutionOutcome(status="failed", response="nope", error="boom")
    max_steps = ExecutionOutcome(status="max_steps_exceeded", response="partial")

    assert completed.is_completed
    assert not failed.is_completed
    assert not max_steps.is_completed
