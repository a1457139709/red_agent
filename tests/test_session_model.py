from models.session import (
    Session,
    SessionMode,
    SessionPersistenceMode,
    SessionStatus,
    SessionTarget,
    SessionTargetKind,
)


def test_session_model_creation_defaults_and_target_summary():
    session = Session.create(
        title="Example Recon",
        goal="Inspect the exposed surface",
        mode=SessionMode.REDTEAM,
        persistence_mode=SessionPersistenceMode.PERSISTENT,
        workspace="C:/workspace",
        targets=[
            SessionTarget(kind=SessionTargetKind.DOMAIN, value="example.com"),
            SessionTarget(kind=SessionTargetKind.IP, value="93.184.216.34"),
        ],
    )

    assert session.public_id == ""
    assert session.status == SessionStatus.DRAFT
    assert session.target_summary == "example.com, 93.184.216.34"
    assert session.metadata == {}
    assert not session.is_terminal


def test_session_model_round_trips_row_payload():
    session = Session(
        id="session-1",
        public_id="S0001",
        title="Internal API Review",
        goal="Assess the staging API surface",
        mode=SessionMode.NORMAL,
        persistence_mode=SessionPersistenceMode.EPHEMERAL,
        workspace="C:/workspace",
        status=SessionStatus.ACTIVE,
        targets=[SessionTarget(kind=SessionTargetKind.URL, value="https://example.com/api")],
        target_summary=None,
        authorization_note="Authorized for staging only.",
        last_error=None,
        metadata={"source": "test"},
    )

    restored = Session.from_row(session.to_row())

    assert restored.public_id == "S0001"
    assert restored.mode == SessionMode.NORMAL
    assert restored.persistence_mode == SessionPersistenceMode.EPHEMERAL
    assert restored.status == SessionStatus.ACTIVE
    assert restored.targets[0].kind == SessionTargetKind.URL
    assert restored.target_summary == "https://example.com/api"
    assert restored.metadata == {"source": "test"}


def test_session_model_rejects_empty_required_fields():
    try:
        Session.create(
            title=" ",
            goal="Goal",
            mode=SessionMode.NORMAL,
            persistence_mode=SessionPersistenceMode.EPHEMERAL,
            workspace="C:/workspace",
        )
    except ValueError as exc:
        assert "title" in str(exc)
    else:
        raise AssertionError("Expected title validation to fail")

    try:
        Session.create(
            title="Title",
            goal=" ",
            mode=SessionMode.NORMAL,
            persistence_mode=SessionPersistenceMode.EPHEMERAL,
            workspace="C:/workspace",
        )
    except ValueError as exc:
        assert "goal" in str(exc)
    else:
        raise AssertionError("Expected goal validation to fail")


def test_session_target_rejects_invalid_kind_and_empty_value():
    try:
        SessionTarget(kind="email", value="user@example.com")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid target kind to fail")

    try:
        SessionTarget(kind=SessionTargetKind.DOMAIN, value=" ")
    except ValueError as exc:
        assert "target value" in str(exc)
    else:
        raise AssertionError("Expected empty target value to fail")


def test_session_status_transition_rules_are_enforced():
    assert Session.can_transition(SessionStatus.DRAFT, SessionStatus.ACTIVE)
    assert not Session.can_transition(SessionStatus.COMPLETED, SessionStatus.ACTIVE)

    try:
        Session.require_valid_transition(SessionStatus.FAILED, SessionStatus.ACTIVE)
    except ValueError as exc:
        assert "failed -> active" in str(exc)
    else:
        raise AssertionError("Expected invalid transition to fail")
