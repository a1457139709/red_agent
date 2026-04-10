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
        "timestamp": "2026-04-09T10:00:00+00:00",
    }


def test_execution_outcome_is_completed_only_for_success():
    completed = ExecutionOutcome(status="completed", response="ok")
    failed = ExecutionOutcome(status="failed", response="nope", error="boom")
    max_steps = ExecutionOutcome(status="max_steps_exceeded", response="partial")

    assert completed.is_completed
    assert not failed.is_completed
    assert not max_steps.is_completed
