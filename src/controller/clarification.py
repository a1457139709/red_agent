from __future__ import annotations

from dataclasses import dataclass

from .contracts import ClarificationAnswer, ClarificationKind, ClarificationRequest
from .intents import extract_record_scope


@dataclass(slots=True)
class ClarificationResolution:
    resolved_record_scope: str | None = None
    next_request: ClarificationRequest | None = None


def build_clarification_request(
    *,
    kind: ClarificationKind,
    original_request: str,
    target_label: str | None = None,
    context: dict[str, str] | None = None,
) -> ClarificationRequest:
    context = dict(context or {})
    if target_label:
        context.setdefault("target", target_label)

    question = "Which session should I use? Say 'current', 'latest', or provide a session id like S0001."
    missing_fields = ["session_scope"]

    return ClarificationRequest(
        kind=kind,
        question=question,
        missing_fields=missing_fields,
        original_request=original_request,
        context=context,
    )


def apply_clarification_answer(
    request: ClarificationRequest,
    raw_answer: str,
) -> ClarificationResolution:
    answer = ClarificationAnswer(
        request_id=request.request_id,
        kind=request.kind,
        raw_answer=raw_answer,
    )
    if answer.kind == ClarificationKind.RECORD_SCOPE:
        return _resolve_record_scope(request, answer)
    return ClarificationResolution(
        next_request=build_clarification_request(
            kind=ClarificationKind.RECORD_SCOPE,
            original_request=request.original_request,
            context=request.context,
        )
    )


def _resolve_record_scope(
    request: ClarificationRequest,
    answer: ClarificationAnswer,
) -> ClarificationResolution:
    scope = extract_record_scope(answer.raw_answer)
    if scope is None:
        return ClarificationResolution(
            next_request=build_clarification_request(
                kind=ClarificationKind.RECORD_SCOPE,
                original_request=request.original_request,
                context=request.context,
            )
        )
    return ClarificationResolution(resolved_record_scope=scope)
