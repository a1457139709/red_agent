from __future__ import annotations

from dataclasses import dataclass
import re

from app.report_flow_service import ReportFlowService
from app.session_record_query_service import SessionRecordQueryService
from app.session_service import SessionService
from models.session import Session, SessionMode, SessionStatus, SessionTarget

from .clarification import apply_clarification_answer, build_clarification_request
from .contracts import (
    ClarificationKind,
    ControllerIntent,
    ControllerRequest,
    ControllerResult,
    ExecutionBridge,
    ExecutionBridgeKind,
    FindingExplanationPayload,
    GeneratedReportPayload,
    RecordLookupKind,
    RecordLookupPayload,
    RecordQueryRequest,
    SessionSummary,
)
from .intents import IntentClassification, classify_input, extract_targets


SESSION_START_KEYWORDS = ("start", "create", "new session", "open session")
DEFAULT_MODULE_NAMES = ("surface-recon", "web-enum")
MODULE_INVOCATION_VERBS = ("run", "use", "invoke", "execute")


@dataclass(slots=True)
class AgentController:
    session_service: SessionService
    session_record_query_service: SessionRecordQueryService
    report_flow_service: ReportFlowService
    module_names: tuple[str, ...] = DEFAULT_MODULE_NAMES

    @classmethod
    def from_session_service(
        cls,
        session_service: SessionService,
        *,
        module_names: tuple[str, ...] = DEFAULT_MODULE_NAMES,
    ) -> "AgentController":
        return cls(
            session_service=session_service,
            session_record_query_service=SessionRecordQueryService.from_settings(session_service.settings),
            report_flow_service=ReportFlowService.from_settings(session_service.settings),
            module_names=module_names,
        )

    def handle(self, request: ControllerRequest) -> ControllerResult:
        if request.pending_clarification is not None:
            return self._handle_clarification(request)
        if request.record_query is not None:
            return self._handle_structured_record_query(request)

        classification = classify_input(request.raw_input)
        if classification.intent == ControllerIntent.ADVANCED_COMMAND_REQUEST:
            return ControllerResult.delegated_to_advanced_command()
        if classification.intent == ControllerIntent.UNSUPPORTED_REQUEST:
            return ControllerResult.unsupported(
                message=classification.unsupported_reason
                or "I couldn't route that request."
            )
        module_request = self._parse_explicit_module_request(request.raw_input)
        if module_request is not None:
            module_name, module_parameters, targets = module_request
            return self._handle_module_request(
                request=request,
                module_name=module_name,
                module_parameters=module_parameters,
                targets=targets,
            )
        if classification.intent == ControllerIntent.RECORD_LOOKUP_REQUEST:
            return self._handle_record_lookup(request, classification)
        return self._handle_session_request(
            request=request,
            classification=classification,
            mode=request.requested_session_mode,
            execute=True,
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
            return self._handle_record_query(
                request=request,
                record_query=RecordQueryRequest(
                    kind=RecordLookupKind.SESSION_HISTORY,
                    explicit_scope=resolution.resolved_record_scope,
                ),
            )
        return ControllerResult.unsupported(
            message="I still need a session scope like current, latest, or S0001."
        )

    def _handle_record_lookup(
        self,
        request: ControllerRequest,
        classification: IntentClassification,
    ) -> ControllerResult:
        return self._handle_record_query(
            request=request,
            record_query=RecordQueryRequest(
                kind=RecordLookupKind.SESSION_HISTORY,
                explicit_scope=classification.explicit_record_scope,
            ),
        )

    def _handle_structured_record_query(
        self,
        request: ControllerRequest,
    ) -> ControllerResult:
        if request.record_query is None:
            return ControllerResult.unsupported(
                message="Missing record query request."
            )
        return self._handle_record_query(
            request=request,
            record_query=request.record_query,
        )

    def _handle_record_query(
        self,
        *,
        request: ControllerRequest,
        record_query: RecordQueryRequest,
    ) -> ControllerResult:
        resolved_scope = record_query.explicit_scope or request.active_session_public_id
        if resolved_scope is None:
            clarification = build_clarification_request(
                kind=ClarificationKind.RECORD_SCOPE,
                original_request=request.raw_input,
            )
            return ControllerResult.clarification_required(
                message=clarification.question,
                clarification_request=clarification,
            )

        session = self._resolve_record_lookup_session(request=request, scope=resolved_scope)
        if session is None:
            return ControllerResult.unsupported(
                message=f"Session not found for record lookup: {resolved_scope}"
            )
        try:
            summary = SessionSummary.from_session(session, reused=True)
            return self._build_record_lookup_result(
                record_query=record_query,
                session_summary=summary,
                resolved_scope=resolved_scope,
            )
        except ValueError as exc:
            return ControllerResult.unsupported(message=str(exc))

    def _resolve_record_lookup_session(
        self,
        *,
        request: ControllerRequest,
        scope: str,
    ) -> Session | None:
        if scope == "current":
            if request.active_session_public_id is None:
                return None
            return self.session_service.get_session(request.active_session_public_id)
        if scope == "latest":
            return self.session_service.get_latest_session()
        return self.session_service.get_session(scope)

    def _build_record_lookup_result(
        self,
        *,
        record_query: RecordQueryRequest,
        session_summary: SessionSummary,
        resolved_scope: str,
    ) -> ControllerResult:
        if record_query.kind == RecordLookupKind.FINDING_EXPLANATION:
            finding_identifier = record_query.lookup_identifier or ""
            explanation = self.session_record_query_service.explain_finding(
                session_summary.id,
                finding_identifier,
            )
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=f"Explained finding {finding_identifier} for session {session_summary.public_id}.",
                session_summary=session_summary,
                finding_explanation_payload=FindingExplanationPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    finding_identifier=finding_identifier,
                    explanation=explanation,
                ),
                bind_session=False,
            )

        if record_query.requests_report_generation:
            report_type = record_query.report_type
            if report_type is None:
                return ControllerResult.unsupported(
                    message="Missing report type for report request."
                )
            if report_type.value == "session_summary":
                report_result = self.report_flow_service.get_or_create_session_summary(session_summary.id)
            elif report_type.value == "findings_summary":
                report_result = self.report_flow_service.get_or_create_findings_summary(session_summary.id)
            else:
                report_result = self.report_flow_service.get_or_create_operator_report(session_summary.id)
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=(
                    f"{'Reused' if report_result.reused else 'Generated'} {report_type.value} report "
                    f"for session {session_summary.public_id}."
                ),
                session_summary=session_summary,
                generated_report_payload=GeneratedReportPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    report_type=report_type,
                    report=report_result.report,
                    reused=report_result.reused,
                    linked_artifact_ids=report_result.linked_artifact_ids,
                    linked_finding_ids=report_result.linked_finding_ids,
                ),
                bind_session=False,
            )

        if record_query.kind == RecordLookupKind.SESSION_HISTORY:
            history_summary = self.session_record_query_service.get_history_summary(session_summary.id)
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=f"Loaded history for session {session_summary.public_id}.",
                session_summary=session_summary,
                record_lookup_payload=RecordLookupPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    history_summary=history_summary,
                ),
                bind_session=False,
            )

        if record_query.kind == RecordLookupKind.EXECUTION_STEPS:
            execution_steps = self.session_record_query_service.list_execution_steps(
                session_summary.id,
            )
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=f"Loaded execution steps for session {session_summary.public_id}.",
                session_summary=session_summary,
                record_lookup_payload=RecordLookupPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    execution_steps=execution_steps,
                ),
                bind_session=False,
            )

        if record_query.kind == RecordLookupKind.ARTIFACTS:
            artifacts = self.session_record_query_service.list_artifacts(
                session_summary.id,
                artifact_identifier=record_query.lookup_identifier,
            )
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=f"Loaded artifacts for session {session_summary.public_id}.",
                session_summary=session_summary,
                record_lookup_payload=RecordLookupPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    artifacts=artifacts,
                ),
                bind_session=False,
            )

        if record_query.kind == RecordLookupKind.FINDINGS:
            findings = self.session_record_query_service.list_findings(
                session_summary.id,
                finding_identifier=record_query.lookup_identifier,
            )
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=f"Loaded findings for session {session_summary.public_id}.",
                session_summary=session_summary,
                record_lookup_payload=RecordLookupPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    findings=findings,
                ),
                bind_session=False,
            )

        if record_query.kind == RecordLookupKind.REPORTS:
            reports = self.session_record_query_service.list_reports(
                session_summary.id,
                report_identifier=record_query.lookup_identifier,
            )
            return ControllerResult.handled(
                intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
                message=f"Loaded reports for session {session_summary.public_id}.",
                session_summary=session_summary,
                record_lookup_payload=RecordLookupPayload(
                    session_summary=session_summary,
                    query=record_query,
                    resolved_scope=resolved_scope,
                    reports=reports,
                ),
                bind_session=False,
            )

        lookup_label = record_query.kind.value.replace("_", " ")
        if record_query.lookup_identifier:
            lookup_label = f"{lookup_label} ({record_query.lookup_identifier})"
        return ControllerResult.handled(
            intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
            message=f"Prepared {lookup_label} lookup for session {session_summary.public_id}.",
            session_summary=session_summary,
            record_lookup_payload=RecordLookupPayload(
                session_summary=session_summary,
                query=record_query,
                resolved_scope=resolved_scope,
            ),
            bind_session=False,
        )

    def _parse_explicit_module_request(
        self,
        raw_input: str,
    ) -> tuple[str, dict[str, object], list[SessionTarget]] | None:
        lowered = raw_input.lower()
        if not any(verb in lowered for verb in MODULE_INVOCATION_VERBS):
            return None
        for module_name in self.module_names:
            pattern = rf"(?<![\w-]){re.escape(module_name.lower())}(?![\w-])"
            if not re.search(pattern, lowered):
                continue
            targets = extract_targets(raw_input)
            if not targets:
                return None
            return module_name, {"target": targets[0].value}, targets
        return None

    def _handle_module_request(
        self,
        *,
        request: ControllerRequest,
        module_name: str,
        module_parameters: dict[str, object],
        targets: list[SessionTarget],
    ) -> ControllerResult:
        session = self._load_active_session(request)
        use_persistent = (
            session is not None
            and session.mode == SessionMode.REDTEAM
            and not session.is_terminal
        )
        summary = (
            SessionSummary.from_session(session, reused=True)
            if use_persistent and session
            else None
        )
        return ControllerResult.handled(
            intent=ControllerIntent.MODULE_INVOCATION_REQUEST,
            message=(
                f"Running module {module_name} in {summary.public_id}."
                if summary is not None
                else f"Running one-shot module {module_name}."
            ),
            session_summary=summary,
            execution_bridge=ExecutionBridge(
                kind=ExecutionBridgeKind.MODULE_RUNTIME,
                prompt_text=self._build_execution_prompt(request.raw_input, targets),
                module_name=module_name,
                module_parameters=module_parameters,
                module_one_shot=summary is None,
            ),
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
