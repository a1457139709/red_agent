from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

from agent.settings import Settings, get_settings
from agent.state import SessionState
from app.capability_service import CapabilityService
from app.interaction_port import InteractionPort
from app.confirmation_policy_service import (
    ConfirmationPolicyService,
    RiskPolicyConfigurationError,
)
from app.session_service import SessionService
from app.tool_access_policy_service import ToolAccessDecisionStatus, ToolAccessPolicyService
from controller.contracts import (
    ConfirmationDecision,
    ConfirmationDecisionValue,
    ConfirmationRequest,
)
from models.conversation_context import ConversationContext
from models.capability import (
    CapabilityExecutionStyle,
    ModuleExecutionPlan,
    ModuleExecutionStep,
    ModuleInvocationRequest,
)
from models.scope_policy import ScopePolicy
from models.risk_policy import ConfirmationRequestPayload, RiskLevel
from models.session import (
    Session,
    SessionMode,
    SessionPersistenceMode,
    SessionStatus,
    SessionTarget,
    SessionTargetKind,
)
from orchestration.scope_validator import AdmissionOutcome, AdmissionRequest, ScopeValidator
from runtime.execution_events import (
    ExecutionEventType,
    ExecutionOutcome,
    ExecutionProgressEvent,
)
from runtime.foreground_runner import ForegroundRunner
from tools import build_security_tool_registry
from tools.executor import (
    SecurityToolExecutionError,
    SecurityToolExecutor,
    ToolExecutionBlockedError,
    ToolExecutionError,
    ToolExecutionGateDecision,
    ToolExecutionRequest,
    ToolExecutor,
)
from tools.policy import RuntimeSafetyPolicy


ProgressCallback = Callable[[ExecutionProgressEvent], None] | None
InfoCallback = Callable[[str], None] | None

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

BASE_SESSION_TOOLS = frozenset(
    {
        "bash",
        "delete_file",
        "edit_file",
        "list_dir",
        "read_file",
        "search",
        "web_fetch",
        "web_search",
        "write_file",
    }
)

SECURITY_TOOL_REGISTRY = build_security_tool_registry()
SECURITY_TOOL_NAMES = frozenset(SECURITY_TOOL_REGISTRY.keys())


@dataclass(slots=True)
class _ThreadsafeInteractionBridge:
    interaction_port: InteractionPort
    conversation_context: ConversationContext
    loop: asyncio.AbstractEventLoop

    def emit_execution_progress(self, event: ExecutionProgressEvent) -> None:
        self._run(self.interaction_port.emit_execution_progress(event, self.conversation_context))

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationDecision:
        return self._run(self.interaction_port.request_confirmation(request, self.conversation_context))

    def emit_confirmation_resolved(self, decision: ConfirmationDecision) -> None:
        self._run(self.interaction_port.emit_confirmation_resolved(decision, self.conversation_context))

    def _run(self, awaitable):
        future = asyncio.run_coroutine_threadsafe(awaitable, self.loop)
        return future.result()


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
        tool_executor: ToolExecutor,
        settings: Settings,
        conversation_context: ConversationContext,
        interaction_port: InteractionPort,
        skill_name: str | None = None,
        on_info: InfoCallback = None,
        on_error: InfoCallback = None,
        capability_service: CapabilityService,
    ) -> ExecutionOutcome:
        try:
            session = self.session_service.require_session(session_identifier)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        try:
            session = self._mark_execution_started(session)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        interaction_bridge = _ThreadsafeInteractionBridge(
            interaction_port=interaction_port,
            conversation_context=conversation_context,
            loop=asyncio.get_running_loop(),
        )
        outcome = await asyncio.to_thread(
            self._run_foreground_execution,
            session=session,
            prompt_text=prompt_text,
            session_state=session_state,
            capability_service=capability_service,
            tool_executor=tool_executor,
            settings=settings,
            interaction_bridge=interaction_bridge,
            skill_name=skill_name,
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

    def _run_foreground_execution(
        self,
        *,
        session: Session,
        prompt_text: str,
        session_state: SessionState,
        capability_service: CapabilityService,
        tool_executor: ToolExecutor,
        settings: Settings,
        interaction_bridge: _ThreadsafeInteractionBridge,
        skill_name: str | None,
        on_info: InfoCallback,
        on_error: InfoCallback,
    ) -> ExecutionOutcome:
        return asyncio.run(
            self.foreground_runner.run(
                session=session,
                prompt_text=prompt_text,
                session_state=session_state,
                capability_service=capability_service,
                tool_executor=tool_executor,
                settings=settings,
                skill_name=skill_name,
                execution_gate=self._build_execution_gate(
                    session=session,
                    interaction_bridge=interaction_bridge,
                ),
                on_progress=self._build_progress_callback(
                    interaction_bridge=interaction_bridge,
                ),
                on_info=on_info,
                on_error=on_error,
            )
        )

    async def execute_module(
        self,
        *,
        invocation: ModuleInvocationRequest,
        tool_executor: ToolExecutor,
        conversation_context: ConversationContext | None = None,
        interaction_port: InteractionPort | None = None,
    ) -> ExecutionOutcome:
        try:
            session = self._resolve_module_session(invocation)
            if not invocation.one_shot:
                session = self._mark_execution_started(session)
            plan = self._build_module_execution_plan(invocation)
        except Exception as exc:
            return self._failed_outcome(str(exc))

        interaction_bridge = None
        if conversation_context is not None and interaction_port is not None:
            interaction_bridge = _ThreadsafeInteractionBridge(
                interaction_port=interaction_port,
                conversation_context=conversation_context,
                loop=asyncio.get_running_loop(),
            )

        return await asyncio.to_thread(
            self._run_module_execution,
            session=session,
            invocation=invocation,
            plan=plan,
            tool_executor=tool_executor,
            interaction_bridge=interaction_bridge,
        )

    def _run_module_execution(
        self,
        *,
        session: Session,
        invocation: ModuleInvocationRequest,
        plan: ModuleExecutionPlan,
        tool_executor: ToolExecutor,
        interaction_bridge: _ThreadsafeInteractionBridge | None,
    ) -> ExecutionOutcome:
        progress_callback = (
            self._build_progress_callback(interaction_bridge=interaction_bridge)
            if interaction_bridge is not None
            else None
        )
        runtime_executor = (
            tool_executor.restricted_to(invocation.allowed_tools)
            .with_safety_policy(RuntimeSafetyPolicy.for_tool_names(invocation.allowed_tools))
            .with_execution_gate(
                self._build_execution_gate(
                    session=session,
                    interaction_bridge=interaction_bridge,
                )
            )
        )

        self._emit_execution_event(
            event_type=ExecutionEventType.EXECUTION_STARTED,
            session=session,
            on_progress=progress_callback,
            message=f"Module {invocation.module.manifest.name} execution started.",
        )

        step_results: list[dict[str, str]] = []
        for step in plan.steps:
            self._emit_execution_event(
                event_type=ExecutionEventType.STEP_STARTED,
                session=session,
                on_progress=progress_callback,
                step_type="module",
                step_label=step.tool_name,
                message=step.summary or f"Run {step.tool_name} for {step.target}.",
            )
            try:
                result = runtime_executor.execute(step.tool_name, step.tool_arguments())
            except ToolExecutionBlockedError as exc:
                return self._finish_module_outcome(
                    session=session,
                    invocation=invocation,
                    outcome=ExecutionOutcome(
                        status="blocked",
                        response=exc.error,
                        error=exc.error,
                        usage={},
                        raw_result={"module": invocation.module.manifest.name, "steps": step_results},
                    ),
                    on_progress=progress_callback,
                )
            except ToolExecutionError as exc:
                return self._finish_module_outcome(
                    session=session,
                    invocation=invocation,
                    outcome=ExecutionOutcome(
                        status="failed",
                        response=exc.error,
                        error=exc.error,
                        usage={},
                        raw_result={"module": invocation.module.manifest.name, "steps": step_results},
                    ),
                    on_progress=progress_callback,
                )
            except Exception as exc:
                error = str(exc)
                return self._finish_module_outcome(
                    session=session,
                    invocation=invocation,
                    outcome=ExecutionOutcome(
                        status="failed",
                        response=error,
                        error=error,
                        usage={},
                        raw_result={"module": invocation.module.manifest.name, "steps": step_results},
                    ),
                    on_progress=progress_callback,
                )

            result_summary = self._summarize_module_step_result(result)
            step_results.append(
                {
                    "tool_name": step.tool_name,
                    "target": step.target,
                    "summary": result_summary,
                }
            )
            self._emit_execution_event(
                event_type=ExecutionEventType.STEP_COMPLETED,
                session=session,
                on_progress=progress_callback,
                step_type="module",
                step_label=step.tool_name,
                message=result_summary,
            )

        response = self._format_module_response(invocation, step_results)
        return self._finish_module_outcome(
            session=session,
            invocation=invocation,
            outcome=ExecutionOutcome(
                status="completed",
                response=response,
                usage={},
                raw_result={
                    "module": invocation.module.manifest.name,
                    "one_shot": invocation.one_shot,
                    "steps": step_results,
                },
            ),
            on_progress=progress_callback,
        )

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

    def _finish_module_outcome(
        self,
        *,
        session: Session,
        invocation: ModuleInvocationRequest,
        outcome: ExecutionOutcome,
        on_progress: ProgressCallback,
    ) -> ExecutionOutcome:
        if outcome.is_completed:
            self._emit_execution_event(
                event_type=ExecutionEventType.EXECUTION_COMPLETED,
                session=session,
                on_progress=on_progress,
                message=f"Module {invocation.module.manifest.name} execution completed.",
            )
        else:
            self._emit_execution_event(
                event_type=(
                    ExecutionEventType.EXECUTION_PAUSED
                    if outcome.status == "blocked"
                    else ExecutionEventType.EXECUTION_FAILED
                ),
                session=session,
                on_progress=on_progress,
                message=outcome.error or outcome.response,
            )
        if not invocation.one_shot:
            try:
                self.session_service.update_session_status(
                    session.id,
                    SessionStatus.ACTIVE,
                    last_error=None if outcome.is_completed else (outcome.error or outcome.response),
                )
            except Exception:
                pass
        return outcome

    def _resolve_module_session(self, invocation: ModuleInvocationRequest) -> Session:
        if invocation.one_shot:
            return self._build_one_shot_module_session(invocation)
        if not invocation.session_id:
            raise ValueError(f"Module '{invocation.module.manifest.name}' requires a session id.")
        return self.session_service.require_session(invocation.session_id)

    def _build_one_shot_module_session(self, invocation: ModuleInvocationRequest) -> Session:
        target_value = str(invocation.parameters.get("target", "")).strip()
        targets = [self._coerce_session_target(target_value)] if target_value else []
        session = Session.create(
            title=f"One-shot module: {invocation.module.manifest.display_name}",
            goal=f"Run module {invocation.module.manifest.name}",
            mode=invocation.mode,
            persistence_mode=SessionPersistenceMode.EPHEMERAL,
            workspace=str(self.session_service.settings.working_directory),
            status=SessionStatus.ACTIVE,
            targets=targets,
            metadata={
                "capability": invocation.module.manifest.name,
                "one_shot": True,
            },
        )
        session.public_id = "one-shot"
        return session

    def _coerce_session_target(self, value: str) -> SessionTarget:
        if "://" in value:
            return SessionTarget(kind=SessionTargetKind.URL, value=value)
        try:
            ip_network(value, strict=False)
        except ValueError:
            pass
        else:
            if "/" in value:
                return SessionTarget(kind=SessionTargetKind.CIDR, value=value)
        try:
            ip_address(value)
        except ValueError:
            pass
        else:
            return SessionTarget(kind=SessionTargetKind.IP, value=value)
        if "." in value:
            return SessionTarget(kind=SessionTargetKind.DOMAIN, value=value)
        return SessionTarget(kind=SessionTargetKind.HOST, value=value)

    def _build_module_execution_plan(
        self,
        invocation: ModuleInvocationRequest,
    ) -> ModuleExecutionPlan:
        if invocation.execution_style == CapabilityExecutionStyle.TYPED_TOOL:
            return self._build_typed_tool_module_plan(invocation)
        if invocation.execution_style == CapabilityExecutionStyle.WORKFLOW:
            return self._build_workflow_module_plan(invocation)
        raise ValueError(
            f"Module '{invocation.module.manifest.name}' cannot be executed as {invocation.execution_style.value}."
        )

    def _build_typed_tool_module_plan(
        self,
        invocation: ModuleInvocationRequest,
    ) -> ModuleExecutionPlan:
        target = self._require_module_target(invocation)
        arguments = {
            key: value
            for key, value in invocation.parameters.items()
            if key != "target"
        }
        return ModuleExecutionPlan(
            invocation=invocation,
            steps=(
                ModuleExecutionStep(
                    tool_name=invocation.execution_profile,
                    target=target,
                    arguments=arguments,
                    summary=f"Run {invocation.execution_profile} for {target}.",
                ),
            ),
        )

    def _build_workflow_module_plan(
        self,
        invocation: ModuleInvocationRequest,
    ) -> ModuleExecutionPlan:
        if invocation.execution_profile == "surface-recon":
            return ModuleExecutionPlan(
                invocation=invocation,
                steps=tuple(self._build_surface_recon_steps(invocation)),
            )
        if invocation.execution_profile == "web-enum":
            return ModuleExecutionPlan(
                invocation=invocation,
                steps=tuple(self._build_web_enum_steps(invocation)),
            )
        raise ValueError(f"Unsupported module workflow profile: {invocation.execution_profile}")

    def _build_surface_recon_steps(
        self,
        invocation: ModuleInvocationRequest,
    ) -> list[ModuleExecutionStep]:
        target = self._parse_module_target(self._require_module_target(invocation))
        include_dns = bool(invocation.parameters.get("include_dns", True))
        include_http = bool(invocation.parameters.get("include_http", True))
        include_tls = bool(invocation.parameters.get("include_tls", True))

        steps: list[ModuleExecutionStep] = []
        if include_dns and not target["is_ip_literal"]:
            steps.append(
                ModuleExecutionStep(
                    tool_name="dns_lookup",
                    target=str(target["host"]),
                    arguments={"record_type": "A"},
                    summary=f"Resolve DNS records for {target['host']}.",
                )
            )
        if include_http:
            for probe_url in self._derive_probe_urls(target):
                steps.append(
                    ModuleExecutionStep(
                        tool_name="http_probe",
                        target=probe_url,
                        arguments={"method": "GET"},
                        summary=f"Probe {probe_url}.",
                    )
                )
        if include_tls:
            tls_target = self._derive_tls_target(target)
            if tls_target is not None:
                steps.append(
                    ModuleExecutionStep(
                        tool_name="tls_inspect",
                        target=tls_target,
                        arguments={},
                        summary=f"Inspect TLS for {tls_target}.",
                    )
                )
        return self._dedupe_module_steps(steps)

    def _build_web_enum_steps(
        self,
        invocation: ModuleInvocationRequest,
    ) -> list[ModuleExecutionStep]:
        target = self._parse_module_target(self._require_module_target(invocation))
        include_tls = bool(invocation.parameters.get("include_tls", True))
        paths = invocation.parameters.get("paths", ["/", "/robots.txt", "/.well-known/security.txt"])
        if not isinstance(paths, list):
            raise ValueError("paths must be a list.")

        steps: list[ModuleExecutionStep] = []
        seen_tls_targets: set[str] = set()
        for base_url in self._derive_probe_urls(target):
            for path in paths:
                probe_url = self._join_url_path(base_url, str(path))
                steps.append(
                    ModuleExecutionStep(
                        tool_name="http_probe",
                        target=probe_url,
                        arguments={"method": "GET"},
                        summary=f"Enumerate {probe_url}.",
                    )
                )
            if include_tls and base_url.startswith("https://"):
                tls_target = self._derive_tls_target_from_url(base_url)
                if tls_target is not None and tls_target not in seen_tls_targets:
                    seen_tls_targets.add(tls_target)
                    steps.append(
                        ModuleExecutionStep(
                            tool_name="tls_inspect",
                            target=tls_target,
                            arguments={},
                            summary=f"Inspect TLS for {tls_target}.",
                        )
                    )
        return self._dedupe_module_steps(steps)

    def _require_module_target(self, invocation: ModuleInvocationRequest) -> str:
        target = str(invocation.parameters.get("target", "")).strip()
        if not target:
            raise ValueError(f"Module '{invocation.module.manifest.name}' requires a target parameter.")
        return target

    def _parse_module_target(self, raw_target: str) -> dict[str, object]:
        if "://" in raw_target:
            parsed = urlsplit(raw_target)
            if not parsed.hostname:
                raise ValueError("URL target must include a host.")
            return {
                "raw_target": raw_target,
                "host": parsed.hostname,
                "is_url": True,
                "is_ip_literal": self._looks_like_ip_literal(parsed.hostname),
                "scheme": parsed.scheme.lower(),
                "port": parsed.port,
                "base_url": f"{parsed.scheme}://{parsed.netloc}",
            }
        host = raw_target
        port = None
        if ":" in raw_target:
            parsed = urlsplit(f"//{raw_target}")
            host = parsed.hostname or raw_target
            port = parsed.port
        return {
            "raw_target": raw_target,
            "host": host,
            "is_url": False,
            "is_ip_literal": self._looks_like_ip_literal(host),
            "scheme": None,
            "port": port,
            "base_url": None,
        }

    def _derive_probe_urls(self, target: dict[str, object]) -> list[str]:
        if target["is_url"] and target["base_url"] is not None:
            return [str(target["base_url"])]
        host = str(target["host"])
        port = target["port"]
        if port is None:
            return [self._build_url("http", host, None), self._build_url("https", host, None)]
        port_value = int(port)
        if port_value == 80:
            return [self._build_url("http", host, port_value)]
        if port_value == 443:
            return [self._build_url("https", host, port_value)]
        return [self._build_url("http", host, port_value), self._build_url("https", host, port_value)]

    def _derive_tls_target(self, target: dict[str, object]) -> str | None:
        if target["is_url"] and target["scheme"] == "https":
            return self._derive_tls_target_from_url(str(target["base_url"] or target["raw_target"]))
        host = str(target["host"])
        port = target["port"]
        if port is not None and not target["is_url"]:
            return f"{host}:{int(port)}"
        return f"{host}:443"

    def _derive_tls_target_from_url(self, value: str) -> str | None:
        parsed = urlsplit(value)
        if not parsed.hostname:
            return None
        return f"{parsed.hostname}:{parsed.port or 443}"

    def _build_url(self, scheme: str, host: str, port: int | None) -> str:
        default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
        netloc = f"[{host}]" if ":" in host and not host.startswith("[") else host
        if port is not None and port != default_port:
            netloc = f"{netloc}:{port}"
        return f"{scheme}://{netloc}"

    def _join_url_path(self, base_url: str, path: str) -> str:
        normalized_path = path.strip() or "/"
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        if normalized_path == "/":
            return base_url
        return f"{base_url}{normalized_path}"

    def _looks_like_ip_literal(self, value: str) -> bool:
        try:
            ip_address(value)
        except ValueError:
            return False
        return True

    def _dedupe_module_steps(self, steps: list[ModuleExecutionStep]) -> list[ModuleExecutionStep]:
        deduped: list[ModuleExecutionStep] = []
        seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
        for step in steps:
            signature = (
                step.tool_name,
                step.target,
                tuple((key, repr(value)) for key, value in sorted(step.arguments.items())),
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(step)
        return deduped

    def _summarize_module_step_result(self, result: object) -> str:
        text = str(result)
        first_line = text.splitlines()[0] if text else ""
        if len(first_line) <= 200:
            return first_line
        return first_line[:197] + "..."

    def _format_module_response(
        self,
        invocation: ModuleInvocationRequest,
        step_results: list[dict[str, str]],
    ) -> str:
        lines = [
            f"Module {invocation.module.manifest.name} completed {len(step_results)} step(s)."
        ]
        for result in step_results:
            lines.append(
                f"- {result['tool_name']} {result['target']}: {result['summary']}"
            )
        return "\n".join(lines)

    def _emit_execution_event(
        self,
        *,
        event_type: ExecutionEventType,
        session: Session,
        on_progress: ProgressCallback,
        step_type: str | None = None,
        step_label: str | None = None,
        message: str | None = None,
    ) -> None:
        if on_progress is None:
            return
        on_progress(
            ExecutionProgressEvent(
                event_type=event_type,
                session_id=session.id,
                session_public_id=session.public_id,
                step_type=step_type,
                step_label=step_label,
                target_summary=session.target_summary,
                message=message,
            )
        )

    def _build_execution_gate(
        self,
        *,
        session: Session,
        interaction_bridge: _ThreadsafeInteractionBridge | None,
    ):
        confirmation_policy_service = self.confirmation_policy_service
        tool_access_policy_service = self.tool_access_policy_service
        security_tool_executor = SecurityToolExecutor(SECURITY_TOOL_REGISTRY)
        scope_validator = ScopeValidator()
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
                    session=session,
                    interaction_bridge=interaction_bridge,
                ):
                    return ToolExecutionGateDecision(
                        status="deny",
                        reason="tool_access_confirmation_denied",
                        message=f"Blocked {request.tool_name}: confirmation denied.",
                    )

            if session.mode != SessionMode.REDTEAM:
                return None

            scope_decision = self._enforce_security_tool_scope(
                request=request,
                session=session,
                security_tool_executor=security_tool_executor,
                scope_validator=scope_validator,
            )
            if scope_decision is not None:
                return scope_decision

            if not self._should_apply_redteam_risk_policy(request.tool_name):
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
                session=session,
                interaction_bridge=interaction_bridge,
            ):
                return None
            return ToolExecutionGateDecision(
                status="deny",
                reason="risk_confirmation_denied",
                message=f"Blocked {request.tool_name}: user denied confirmation.",
            )

        return gate

    def _should_apply_redteam_risk_policy(self, tool_name: str) -> bool:
        if tool_name in RISK_SCOPED_ACTIONS:
            return True
        if tool_name in BASE_SESSION_TOOLS:
            return False
        return True

    def _enforce_security_tool_scope(
        self,
        *,
        request: ToolExecutionRequest,
        session: Session,
        security_tool_executor: SecurityToolExecutor,
        scope_validator: ScopeValidator,
    ) -> ToolExecutionGateDecision | None:
        if request.tool_name not in SECURITY_TOOL_NAMES:
            return None

        target = str(request.args.get("target", "")).strip()
        if not target:
            return ToolExecutionGateDecision(
                status="deny",
                reason="security_tool_target_missing",
                message=f"Blocked {request.tool_name}: target is required.",
            )

        try:
            tool = security_tool_executor.get_tool(request.tool_name)
            policy = self._build_session_scope_policy(
                session=session,
                tool_category=tool.category,
            )
            invocation = security_tool_executor.validate(
                request.tool_name,
                target=target,
                arguments=request.args,
                policy=policy,
            )
        except SecurityToolExecutionError as exc:
            return ToolExecutionGateDecision(
                status="deny",
                reason="security_tool_validation_failed",
                message=f"Blocked {request.tool_name}: {exc.error}",
            )
        except Exception as exc:
            return ToolExecutionGateDecision(
                status="deny",
                reason="security_tool_validation_failed",
                message=f"Blocked {request.tool_name}: {exc}",
            )

        if request.tool_name == "dns_lookup":
            admission_request = AdmissionRequest(
                session_id=session.id,
                job_id=None,
                tool_name=tool.name,
                tool_category=tool.category,
                raw_target=target,
                protocol="dns",
                port=53,
                metadata=dict(invocation.metadata),
            )
        else:
            admission_request = invocation.to_admission_request(
                session_id=session.id,
                job_id=None,
                tool_name=tool.name,
                tool_category=tool.category,
            )
        decision = scope_validator.evaluate(policy, admission_request)
        if decision.outcome == AdmissionOutcome.ALLOWED:
            return None
        reason = (
            "security_tool_scope_confirmation_required"
            if decision.outcome == AdmissionOutcome.REQUIRES_CONFIRMATION
            else "security_tool_scope_denied"
        )
        return ToolExecutionGateDecision(
            status="deny",
            reason=reason,
            message=f"Blocked {request.tool_name}: {decision.message}",
        )

    def _build_session_scope_policy(
        self,
        *,
        session: Session,
        tool_category: str,
    ) -> ScopePolicy:
        allowed_hosts: list[str] = []
        allowed_domains: list[str] = []
        allowed_cidrs: list[str] = []
        allowed_protocols: list[str] = []
        allowed_ports: list[int] = []

        for target in session.targets:
            self._append_session_target_constraints(
                target=target,
                allowed_hosts=allowed_hosts,
                allowed_domains=allowed_domains,
                allowed_cidrs=allowed_cidrs,
                allowed_protocols=allowed_protocols,
                allowed_ports=allowed_ports,
            )

        return ScopePolicy.create(
            session_id=session.id,
            allowed_hosts=self._dedupe_ordered(allowed_hosts),
            allowed_domains=self._dedupe_ordered(allowed_domains),
            allowed_cidrs=self._dedupe_ordered(allowed_cidrs),
            allowed_protocols=self._dedupe_ordered(allowed_protocols),
            allowed_ports=self._dedupe_ordered(allowed_ports),
            allowed_tool_categories=[tool_category],
        )

    def _append_session_target_constraints(
        self,
        *,
        target: SessionTarget,
        allowed_hosts: list[str],
        allowed_domains: list[str],
        allowed_cidrs: list[str],
        allowed_protocols: list[str],
        allowed_ports: list[int],
    ) -> None:
        value = target.value.strip()
        if not value:
            return

        if target.kind == SessionTargetKind.DOMAIN:
            allowed_domains.append(value)
            return
        if target.kind == SessionTargetKind.CIDR:
            allowed_cidrs.append(value)
            return
        if target.kind in {SessionTargetKind.HOST, SessionTargetKind.IP}:
            allowed_hosts.append(value)
            return
        if target.kind != SessionTargetKind.URL:
            return

        parsed = urlsplit(value)
        if parsed.hostname:
            allowed_hosts.append(parsed.hostname)
        if parsed.scheme:
            allowed_protocols.append(parsed.scheme.lower())
        if parsed.port:
            allowed_ports.append(parsed.port)

    def _dedupe_ordered(self, values: list[str] | list[int]) -> list[str] | list[int]:
        seen: set[str | int] = set()
        deduped: list[str | int] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _request_confirmation(
        self,
        *,
        payload: ConfirmationRequestPayload,
        session: Session,
        interaction_bridge: _ThreadsafeInteractionBridge | None,
    ) -> bool:
        if interaction_bridge is None:
            return False
        self._emit_confirmation_event(
            event_type=ExecutionEventType.CONFIRMATION_REQUIRED,
            payload=payload,
            interaction_bridge=interaction_bridge,
            session=session,
        )
        decision = interaction_bridge.request_confirmation(
            self._build_confirmation_request(payload),
        )
        interaction_bridge.emit_confirmation_resolved(decision)
        approved = decision.decision == ConfirmationDecisionValue.APPROVE
        self._emit_confirmation_event(
            event_type=(
                ExecutionEventType.CONFIRMATION_APPROVED
                if approved
                else ExecutionEventType.CONFIRMATION_DENIED
            ),
            payload=payload,
            interaction_bridge=interaction_bridge,
            session=session,
        )
        return approved

    def _build_confirmation_request(
        self,
        payload: ConfirmationRequestPayload,
    ) -> ConfirmationRequest:
        return ConfirmationRequest(
            action_name=payload.action_name,
            risk_level=payload.risk_level.value,
            target_summary=payload.target_summary,
            reason=payload.reason,
            message=payload.message,
        )

    def _build_progress_callback(
        self,
        *,
        interaction_bridge: _ThreadsafeInteractionBridge,
    ) -> Callable[[ExecutionProgressEvent], None]:
        def emit(event: ExecutionProgressEvent) -> None:
            interaction_bridge.emit_execution_progress(event)

        return emit

    def _emit_confirmation_event(
        self,
        *,
        event_type: ExecutionEventType,
        payload: ConfirmationRequestPayload,
        interaction_bridge: _ThreadsafeInteractionBridge | None,
        session: Session,
    ) -> None:
        if interaction_bridge is None:
            return
        interaction_bridge.emit_execution_progress(
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
