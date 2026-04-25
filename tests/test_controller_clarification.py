from controller.clarification import apply_clarification_answer, build_clarification_request
from controller.contracts import ClarificationKind


def test_build_clarification_request_for_record_scope_mentions_scope_options():
    request = build_clarification_request(
        kind=ClarificationKind.RECORD_SCOPE,
        original_request="what did you already do",
    )

    assert request.kind == ClarificationKind.RECORD_SCOPE
    assert "current" in request.question
    assert request.missing_fields == ["session_scope"]


def test_apply_clarification_answer_reasks_for_record_scope_when_answer_is_invalid():
    request = build_clarification_request(
        kind=ClarificationKind.RECORD_SCOPE,
        original_request="what did you already do",
    )

    resolution = apply_clarification_answer(request, "yes")

    assert resolution.next_request is not None
    assert resolution.next_request.kind == ClarificationKind.RECORD_SCOPE


def test_apply_clarification_answer_resolves_record_scope():
    request = build_clarification_request(
        kind=ClarificationKind.RECORD_SCOPE,
        original_request="what did you already do",
    )

    resolution = apply_clarification_answer(request, "latest")

    assert resolution.resolved_record_scope == "latest"
    assert resolution.next_request is None
