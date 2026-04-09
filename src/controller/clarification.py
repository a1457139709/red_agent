from __future__ import annotations

from dataclasses import dataclass

from models.session import SessionMode, SessionTarget

from .contracts import ClarificationAnswer, ClarificationKind, ClarificationRequest
from .intents import extract_record_scope, extract_targets, infer_persistence_mode_from_answer


@dataclass(slots=True)
class ClarificationResolution:
    resolved_mode: SessionMode | None = None
    resolved_targets: list[SessionTarget] | None = None
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

    if kind == ClarificationKind.BARE_TARGET:
        question = (
            f"Do you want a one-off check or a persistent redteam session for {target_label or 'that target'}?"
        )
        missing_fields = ["mode"]
    elif kind == ClarificationKind.MISSING_TARGET:
        question = "Which target should I use, and should this be a one-off check or a persistent redteam session?"
        missing_fields = ["target", "mode"]
    elif kind == ClarificationKind.PERSISTENCE_MODE:
        question = (
            f"Should {target_label or 'this'} be a one-off check or a persistent redteam session?"
        )
        missing_fields = ["mode"]
    else:
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
    if answer.kind == ClarificationKind.MISSING_TARGET:
        return _resolve_missing_target(request, answer)
    if answer.kind in {ClarificationKind.BARE_TARGET, ClarificationKind.PERSISTENCE_MODE}:
        return _resolve_persistence_mode(request, answer)
    return ClarificationResolution(
        next_request=build_clarification_request(
            kind=request.kind,
            original_request=request.original_request,
            target_label=request.context.get("target"),
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


def _resolve_missing_target(
    request: ClarificationRequest,
    answer: ClarificationAnswer,
) -> ClarificationResolution:
    targets = extract_targets(answer.raw_answer)
    if not targets:
        return ClarificationResolution(
            next_request=build_clarification_request(
                kind=ClarificationKind.MISSING_TARGET,
                original_request=request.original_request,
                context=request.context,
            )
        )

    mode_label = infer_persistence_mode_from_answer(answer.raw_answer)
    if mode_label is None:
        return ClarificationResolution(
            next_request=build_clarification_request(
                kind=ClarificationKind.PERSISTENCE_MODE,
                original_request=request.original_request,
                target_label=targets[0].value,
                context={"target": targets[0].value},
            )
        )
    return ClarificationResolution(
        resolved_targets=targets,
        resolved_mode=_mode_from_label(mode_label),
    )


def _resolve_persistence_mode(
    request: ClarificationRequest,
    answer: ClarificationAnswer,
) -> ClarificationResolution:
    mode_label = infer_persistence_mode_from_answer(answer.raw_answer)
    if mode_label is None:
        return ClarificationResolution(
            next_request=build_clarification_request(
                kind=ClarificationKind.PERSISTENCE_MODE,
                original_request=request.original_request,
                target_label=request.context.get("target"),
                context=request.context,
            )
        )

    targets = extract_targets(request.original_request)
    if not targets and request.context.get("target"):
        targets = [SessionTarget(kind="host", value=request.context["target"])]
    return ClarificationResolution(
        resolved_targets=targets or None,
        resolved_mode=_mode_from_label(mode_label),
    )


def _mode_from_label(label: str) -> SessionMode:
    if label == "redteam":
        return SessionMode.REDTEAM
    return SessionMode.NORMAL
