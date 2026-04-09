from controller.clarification import apply_clarification_answer, build_clarification_request
from controller.contracts import ClarificationKind
from models.session import SessionMode


def test_build_clarification_request_for_bare_target_mentions_target():
    request = build_clarification_request(
        kind=ClarificationKind.BARE_TARGET,
        original_request="look at example.com",
        target_label="example.com",
    )

    assert request.kind == ClarificationKind.BARE_TARGET
    assert "example.com" in request.question
    assert request.missing_fields == ["mode"]


def test_apply_clarification_answer_resolves_missing_target_and_mode():
    request = build_clarification_request(
        kind=ClarificationKind.MISSING_TARGET,
        original_request="scan this host",
    )

    resolution = apply_clarification_answer(request, "Use example.com as a persistent redteam session")

    assert resolution.next_request is None
    assert resolution.resolved_mode == SessionMode.REDTEAM
    assert resolution.resolved_targets is not None
    assert resolution.resolved_targets[0].value == "example.com"


def test_apply_clarification_answer_requests_follow_up_when_mode_stays_ambiguous():
    request = build_clarification_request(
        kind=ClarificationKind.BARE_TARGET,
        original_request="look at example.com",
        target_label="example.com",
    )

    resolution = apply_clarification_answer(request, "yes")

    assert resolution.resolved_mode is None
    assert resolution.next_request is not None
    assert resolution.next_request.kind == ClarificationKind.PERSISTENCE_MODE


def test_apply_clarification_answer_resolves_record_scope():
    request = build_clarification_request(
        kind=ClarificationKind.RECORD_SCOPE,
        original_request="what did you already do",
    )

    resolution = apply_clarification_answer(request, "latest")

    assert resolution.resolved_record_scope == "latest"
    assert resolution.next_request is None
