from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent.settings import Settings, get_settings
from agent.state import SessionState
from app.confirmation_policy_service import (
    ConfirmationPolicyService,
    RiskPolicyConfigurationError,
)
from app.session_service import SessionService
from app.skill_service import SkillService
from app.tool_access_policy_service import ToolAccessDecisionStatus, ToolAccessPolicyService
from models.risk_policy import ConfirmationRequestPayload, RiskLevel
from models.session import Session, SessionMode, SessionStatus
from runtime.execution_events import (
    ExecutionEventType,
    ExecutionOutcome,
    ExecutionProgressEvent,
)
from runtime.foreground_runner import ForegroundRunner
from tools.executor import (
    ToolExecutionGateDecision,
    ToolExecutionRequest,
    ToolExecutor,
)


ProgressCallback = Callable[[ExecutionProgressEvent], None] | None
InfoCallback = Callable[[str], None] | None
ConfirmationCallback = Callable[[ConfirmationRequestPayload], bool] | None

RISK_SCOPED_ACTIONS = {
    "dns_lookup",
    "http_probe",
    "tls_inspect",
    "banner_grab",
    "port_scan",
    "port_scan_small",
    "port_scan_large",
    "batch_safe_probe",
    "batch_probe",
    "directory_scan_large",
    "poc_execute",
}


@dataclass(slots=True)
class ExecutionService:
    session_service: SessionService
    foreground_runner: ForegroundRunner
    confirmation_policy_service: ConfirmationPolicyService | None = None
    tool_access_policy_service: ToolAccessPolicyService | None = None

    def __post_init__(self) -> None:
        if self.confirmation_policy_service is None:
            self.confirmation_policy_service = ConfirmationPolicyService.from_settings(
                self.session_service.settings
            )
        if self.tool_access_policy_service is None:
            self.tool_access_policy_service = ToolAccessPolicyService()

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        session_service: SessionService | None = None,
        foreground_runner: ForegroundRunner | None = None,
        confirmation_policy_service: ConfirmationPolicyService | None = None,
        tool_access_policy_service: ToolAccessPolicyService | None = None,
    ) -> "ExecutionService":
        settings = settings or get_settings()
        return cls(
            session_service=session_service or SessionService.from_settings(settings),
            foreground_runner=foreground_runner or ForegroundRunner(),
            confirmation_policy_service=confirmation_policy_service
            or ConfirmationPolicyService.from_settings(settings),
            tool_access_policy_service=tool_access_policy_service or ToolAccessPolicyService(),
        )

    async def execute_session(
        self,
        *,
        session_identifier: str,
        prompt_text: str,
        session_state: SessionState,
        skill_service: SkillService,
        tool_executor: ToolExecutor,
        settings: Settings,
        skill_name: str | None = None,
        on_progress: ProgressCallback = None,
        on_info: InfoCallback = None,
        on_error: InfoCallback = None,
        on_confirmation: ConfirmationCallback = None,
    ) -> ExecutionOutcome:
        try:
            session = self.session_service.require_session(session_identifier)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        try:
            session = self._mark_execution_started(session)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        outcome = await self.foreground_runner.run(
            session=session,
            prompt_text=prompt_text,
            session_state=session_state,
            skill_service=skill_service,
            tool_executor=tool_executor,
            settings=settings,
            skill_name=skill_name,
            execution_gate=self._build_execution_gate(
                session=session,
                on_progress=on_progress,
                on_confirmation=on_confirmation,
            ),
            on_progress=on_progress,
            on_info=on_info,
            on_error=on_error,
        )

        try:
            if outcome.error:
                self.session_service.update_session_status(
                    session.id,
                    SessionStatus.ACTIVE,
                    last_error=outcome.error,
                )
            else:
                self.session_service.update_session_status(
                    session.id,
                    SessionStatus.ACTIVE,
                    last_error=None,
                )
        except Exception:
            # Execution result is still meaningful even if status persistence fails.
            pass

        return outcome

    def _mark_execution_started(self, session: Session) -> Session:
        return self.session_service.update_session_status(
            session.id,
            SessionStatus.ACTIVE,
            last_error=None,
        )

    def _failed_outcome(self, error: str) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="failed",
            response=error,
            error=error,
            usage={},
            raw_result=None,
        )

    def _build_execution_gate(
        self,
        *,
        session: Session,
        on_progress: ProgressCallback,
        on_confirmation: ConfirmationCallback,
    ):
        confirmation_policy_service = self.confirmation_policy_service
        tool_access_policy_service = self.tool_access_policy_service
        assert confirmation_policy_service is not None
        assert tool_access_policy_service is not None

        def gate(request: ToolExecutionRequest) -> ToolExecutionGateDecision | None:
            access_decision = tool_access_policy_service.evaluate_tool_access(
                mode=session.mode,
                tool_name=request.tool_name,
                arguments=request.args,
                workspace=session.workspace,
                session_public_id=session.public_id,
            )
            if access_decision.status == ToolAccessDecisionStatus.DENY:
                return ToolExecutionGateDecision(
                    status="deny",
                    reason=access_decision.reason,
                    message=access_decision.message,
                )
            if access_decision.status == ToolAccessDecisionStatus.CONFIRM:
                payload = ConfirmationRequestPayload(
                    action_name=request.tool_name,
                    risk_level=RiskLevel.ELEVATED,
                    target_summary=session.target_summary,
                    reason=access_decision.reason,
                    message=access_decision.message,
                )
                if not self._request_confirmation(
                    payload=payload,
                    on_progress=on_progress,
                    on_confirmation=on_confirmation,
                    session=session,
                ):
                    return ToolExecutionGateDecision(
                        status="deny",
                        reason="tool_access_confirmation_denied",
                        message=f"Blocked {request.tool_name}: confirmation denied.",
                    )

            if session.mode != SessionMode.REDTEAM:
                return None
            if request.tool_name not in RISK_SCOPED_ACTIONS:
                return None

            try:
                decision, payload = confirmation_policy_service.build_confirmation_decision(
                    action_name=request.tool_name,
                    arguments=request.args,
                    target_summary=session.target_summary,
                )
            except RiskPolicyConfigurationError as exc:
                return ToolExecutionGateDecision(
                    status="deny",
                    reason="risk_policy_invalid",
                    message=f"Blocked {request.tool_name}: {exc}",
                )

            if not decision.requires_confirmation:
                return None
            assert payload is not None
            if self._request_confirmation(
                payload=payload,
                on_progress=on_progress,
                on_confirmation=on_confirmation,
                session=session,
            ):
                return None
            return ToolExecutionGateDecision(
                status="deny",
                reason="risk_confirmation_denied",
                message=f"Blocked {request.tool_name}: user denied confirmation.",
            )

        return gate

    def _request_confirmation(
        self,
        *,
        payload: ConfirmationRequestPayload,
        on_progress: ProgressCallback,
        on_confirmation: ConfirmationCallback,
        session: Session,
    ) -> bool:
        self._emit_confirmation_event(
            event_type=ExecutionEventType.CONFIRMATION_REQUIRED,
            payload=payload,
            on_progress=on_progress,
            session=session,
        )
        approved = False if on_confirmation is None else bool(on_confirmation(payload))
        self._emit_confirmation_event(
            event_type=(
                ExecutionEventType.CONFIRMATION_APPROVED
                if approved
                else ExecutionEventType.CONFIRMATION_DENIED
            ),
            payload=payload,
            on_progress=on_progress,
            session=session,
        )
        return approved

    def _emit_confirmation_event(
        self,
        *,
        event_type: ExecutionEventType,
        payload: ConfirmationRequestPayload,
        on_progress: ProgressCallback,
        session: Session,
    ) -> None:
        if on_progress is None:
            return
        on_progress(
            ExecutionProgressEvent(
                event_type=event_type,
                session_id=session.id,
                session_public_id=session.public_id,
                step_type="confirmation",
                step_label=payload.action_name,
                target_summary=payload.target_summary,
                message=payload.message,
                action_name=payload.action_name,
                risk_level=payload.risk_level.value,
                reason=payload.reason,
            )
        )
