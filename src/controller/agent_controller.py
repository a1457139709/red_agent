from __future__ import annotations

from dataclasses import dataclass

from app.session_service import SessionService
from models.session import Session, SessionMode, SessionStatus, SessionTarget

from .clarification import ClarificationResolution, apply_clarification_answer, build_clarification_request
from .contracts import (
    ClarificationKind,
    ControllerIntent,
    ControllerRequest,
    ControllerResult,
    ExecutionBridge,
    ExecutionBridgeKind,
    SessionSummary,
)
from .intents import IntentClassification, classify_input


SESSION_START_KEYWORDS = ("start", "create", "new session", "open session")


@dataclass(slots=True)
class AgentController:
    session_service: SessionService

    @classmethod
    def from_session_service(cls, session_service: SessionService) -> "AgentController":
        return cls(session_service=session_service)

    def handle(self, request: ControllerRequest) -> ControllerResult:
        if request.pending_clarification is not None:
            return self._handle_clarification(request)

        classification = classify_input(request.raw_input)
        if classification.intent == ControllerIntent.ADVANCED_COMMAND_REQUEST:
            return ControllerResult.delegated_to_advanced_command()
        if classification.intent == ControllerIntent.UNSUPPORTED_REQUEST:
            return ControllerResult.unsupported(
                message=classification.unsupported_reason
                or "I couldn't route that request."
            )
        if classification.intent == ControllerIntent.CLARIFICATION_REQUIRED:
            return self._build_clarification_result(request.raw_input, classification)
        if classification.intent == ControllerIntent.RECORD_LOOKUP_REQUEST:
            return self._handle_record_lookup(request, classification)
        if classification.intent == ControllerIntent.REDTEAM_REQUEST:
            return self._handle_session_request(
                request=request,
                classification=classification,
                mode=SessionMode.REDTEAM,
                execute=True,
            )
        return self._handle_session_request(
            request=request,
            classification=classification,
            mode=SessionMode.NORMAL,
            execute=True,
        )

    def _build_clarification_result(
        self,
        raw_input: str,
        classification: IntentClassification,
    ) -> ControllerResult:
        target_label = classification.extracted_targets[0].value if classification.extracted_targets else None
        clarification = build_clarification_request(
            kind=classification.clarification_kind or ClarificationKind.MISSING_TARGET,
            original_request=raw_input,
            target_label=target_label,
        )
        return ControllerResult.clarification_required(
            message=clarification.question,
            clarification_request=clarification,
        )

    def _handle_clarification(self, request: ControllerRequest) -> ControllerResult:
        resolution = apply_clarification_answer(
            request.pending_clarification,
            request.raw_input,
        )
        if resolution.next_request is not None:
            return ControllerResult.clarification_required(
                message=resolution.next_request.question,
                clarification_request=resolution.next_request,
            )
        if resolution.resolved_record_scope is not None:
            return self._handle_record_lookup_scope(request, resolution.resolved_record_scope)
        if resolution.resolved_mode is None:
            return ControllerResult.unsupported(
                message="I still need enough information to route that request."
            )
        classification = classify_input(request.pending_clarification.original_request)
        return self._handle_session_request(
            request=request,
            classification=classification,
            mode=resolution.resolved_mode,
            execute=resolution.resolved_mode == SessionMode.NORMAL,
            forced_targets=resolution.resolved_targets,
            original_request=request.pending_clarification.original_request,
        )

    def _handle_record_lookup(
        self,
        request: ControllerRequest,
        classification: IntentClassification,
    ) -> ControllerResult:
        if classification.explicit_record_scope is not None:
            return self._handle_record_lookup_scope(request, classification.explicit_record_scope)
        if request.active_session_public_id:
            return self._handle_record_lookup_scope(request, request.active_session_public_id)
        clarification = build_clarification_request(
            kind=ClarificationKind.RECORD_SCOPE,
            original_request=request.raw_input,
        )
        return ControllerResult.clarification_required(
            message=clarification.question,
            clarification_request=clarification,
        )

    def _handle_record_lookup_scope(
        self,
        request: ControllerRequest,
        scope: str,
    ) -> ControllerResult:
        session: Session | None
        if scope == "current":
            if request.active_session_public_id is None:
                clarification = build_clarification_request(
                    kind=ClarificationKind.RECORD_SCOPE,
                    original_request=request.raw_input,
                )
                return ControllerResult.clarification_required(
                    message=clarification.question,
                    clarification_request=clarification,
                )
            session = self.session_service.get_session(request.active_session_public_id)
        elif scope == "latest":
            session = self.session_service.get_latest_session()
        else:
            session = self.session_service.get_session(scope)

        if session is None:
            return ControllerResult.unsupported(
                message=f"Session not found for record lookup: {scope}"
            )

        summary = SessionSummary.from_session(session, reused=True)
        return ControllerResult.handled(
            intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
            message=f"Session {summary.public_id}: {summary.title}",
            session_summary=summary,
            bind_session=False,
        )

    def _handle_session_request(
        self,
        *,
        request: ControllerRequest,
        classification: IntentClassification,
        mode: SessionMode,
        execute: bool,
        forced_targets: list[SessionTarget] | None = None,
        original_request: str | None = None,
    ) -> ControllerResult:
        raw_request = original_request or request.raw_input
        targets = list(forced_targets or classification.extracted_targets)
        session, reused = self._reuse_or_create_session(
            request=request,
            raw_request=raw_request,
            targets=targets,
            mode=mode,
        )
        summary = SessionSummary.from_session(session, reused=reused)
        if execute:
            intent = (
                ControllerIntent.NORMAL_REQUEST
                if mode == SessionMode.NORMAL
                else ControllerIntent.REDTEAM_REQUEST
            )
            session_label = "normal" if mode == SessionMode.NORMAL else "redteam"
            bridge_kind = (
                ExecutionBridgeKind.ACTIVE_SKILL_RUNTIME
                if request.active_skill_name
                else ExecutionBridgeKind.BASE_RUNTIME
            )
            message = None if reused else f"Started {session_label} session {summary.public_id}: {summary.title}"
            return ControllerResult.handled(
                intent=intent,
                message=message,
                session_summary=summary,
                execution_bridge=ExecutionBridge(
                    kind=bridge_kind,
                    prompt_text=self._build_execution_prompt(raw_request, targets),
                ),
                bind_session=True,
            )

        action = "Reused" if reused else "Started"
        return ControllerResult.handled(
            intent=ControllerIntent.REDTEAM_REQUEST,
            message=f"{action} redteam session {summary.public_id}: {summary.title}",
            session_summary=summary,
            bind_session=True,
        )

    def _reuse_or_create_session(
        self,
        *,
        request: ControllerRequest,
        raw_request: str,
        targets: list[SessionTarget],
        mode: SessionMode,
    ) -> tuple[Session, bool]:
        existing = self._load_active_session(request)
        if (
            existing is not None
            and existing.mode == mode
            and not existing.is_terminal
            and not self._should_force_new_session(raw_request, existing, targets)
        ):
            return existing, True

        title = self._derive_session_title(raw_request, targets, mode)
        session = self.session_service.create_session(
            title=title,
            goal=raw_request.strip(),
            mode=mode,
            status=SessionStatus.ACTIVE,
            targets=targets or None,
        )
        return session, False

    def _load_active_session(self, request: ControllerRequest) -> Session | None:
        if request.active_session_public_id is None:
            return None
        return self.session_service.get_session(request.active_session_public_id)

    def _should_force_new_session(
        self,
        raw_request: str,
        existing: Session,
        targets: list[SessionTarget],
    ) -> bool:
        lowered = raw_request.lower()
        if any(keyword in lowered for keyword in SESSION_START_KEYWORDS):
            return True
        if not targets or not existing.target_summary:
            return False
        return targets[0].value not in existing.target_summary

    def _derive_session_title(
        self,
        raw_request: str,
        targets: list[SessionTarget],
        mode: SessionMode,
    ) -> str:
        if targets:
            prefix = "Redteam Session" if mode == SessionMode.REDTEAM else "Session"
            return f"{prefix} for {targets[0].value}"
        preview = " ".join(raw_request.strip().split())
        if len(preview) > 48:
            preview = preview[:45].rstrip() + "..."
        if mode == SessionMode.REDTEAM:
            return f"Redteam: {preview}"
        return f"Session: {preview}"

    def _build_execution_prompt(
        self,
        raw_request: str,
        targets: list[SessionTarget],
    ) -> str:
        if not targets:
            return raw_request
        if all(target.value in raw_request for target in targets):
            return raw_request
        target_lines = [f"- {target.kind.value}: {target.value}" for target in targets]
        return raw_request.rstrip() + "\nTargets:\n" + "\n".join(target_lines)
