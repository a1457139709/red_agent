from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import TargetDescriptor
from tools.contracts import SecurityTool, SecurityToolInvocation, SecurityToolResult
from tools.error_signals import RECOVERABLE_TOOL_ERROR_PREFIX
from tools.factory import ToolDefinition, ToolResultEnvelope
from tools.policy import CapabilityTier, RuntimeSafetyPolicy, SafetyAuditEvent, get_tool_capability
from utils.safety import detect_danger, is_sensitive_path, resolve_safe_path


AuditCallback = Callable[[SafetyAuditEvent], None] | None
ConfirmCallback = Callable[[str], bool] | None
InfoCallback = Callable[[str], None] | None


@dataclass(frozen=True, slots=True)
class ToolExecutionEvent:
    event_type: str
    tool_name: str
    capability: CapabilityTier
    args_summary: str | None = None
    result_summary: str | None = None
    error: str | None = None
    target: str | None = None
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_type": self.event_type,
            "tool_name": self.tool_name,
            "capability": self.capability.value,
        }
        if self.target:
            payload["target"] = self.target
        if self.args_summary:
            payload["args_summary"] = self.args_summary
        if self.result_summary:
            payload["result_summary"] = self.result_summary
        if self.error:
            payload["error"] = self.error
        if self.input_payload:
            payload["input"] = self.input_payload
        if self.output_payload:
            payload["output"] = self.output_payload
        return payload


ToolEventCallback = Callable[[ToolExecutionEvent], None] | None


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    tool_name: str
    capability: CapabilityTier
    args: dict[str, Any]
    target: str | None
    args_summary: str | None


@dataclass(frozen=True, slots=True)
class ToolExecutionGateDecision:
    status: str
    reason: str
    message: str

    @property
    def is_allowed(self) -> bool:
        return self.status == "allow"


ToolExecutionGate = Callable[[ToolExecutionRequest], ToolExecutionGateDecision | None] | None


class ToolExecutionError(RuntimeError):
    def __init__(self, tool_name: str, capability: CapabilityTier, error: str) -> None:
        super().__init__(error)
        self.tool_name = tool_name
        self.capability = capability
        self.error = error


class ToolExecutionBlockedError(ToolExecutionError):
    def __init__(
        self,
        tool_name: str,
        capability: CapabilityTier,
        error: str,
        *,
        reason: str,
    ) -> None:
        super().__init__(tool_name, capability, error)
        self.reason = reason


class SecurityToolExecutionError(RuntimeError):
    def __init__(self, tool_name: str, error: str) -> None:
        super().__init__(error)
        self.tool_name = tool_name
        self.error = error


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    tool_name: str
    capability: CapabilityTier
    target: str | None = None
    args_summary: str | None = None


class ToolExecutor:
    def __init__(
        self,
        tools: dict,
        *,
        confirm_command: ConfirmCallback = None,
        on_info: InfoCallback = None,
        safety_policy: RuntimeSafetyPolicy | None = None,
        on_audit: AuditCallback = None,
        on_tool_event: ToolEventCallback = None,
        execution_gate: ToolExecutionGate = None,
        preferred_shell: str | None = None,
    ) -> None:
        self._tools = tools
        self._confirm_command = confirm_command
        self._on_info = on_info
        self._safety_policy = safety_policy or RuntimeSafetyPolicy.base()
        self._on_audit = on_audit
        self._on_tool_event = on_tool_event
        self._execution_gate = execution_gate
        self._preferred_shell = preferred_shell

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)

    @property
    def safety_policy(self) -> RuntimeSafetyPolicy:
        return self._safety_policy

    def get_tools(self) -> list:
        tools = []
        for tool in self._tools.values():
            if isinstance(tool, ToolDefinition):
                tools.append(tool.build_langchain_tool())
            else:
                tools.append(tool)
        return tools

    def restricted_to(self, allowed_names: list[str] | set[str] | tuple[str, ...]) -> "ToolExecutor":
        allowed = set(allowed_names)
        unknown = sorted(tool_name for tool_name in allowed if tool_name not in self._tools)
        if unknown:
            raise ValueError(f"Unknown tools requested: {', '.join(unknown)}")
        return ToolExecutor(
            {name: tool for name, tool in self._tools.items() if name in allowed},
            confirm_command=self._confirm_command,
            on_info=self._on_info,
            safety_policy=self._safety_policy,
            on_audit=self._on_audit,
            on_tool_event=self._on_tool_event,
            execution_gate=self._execution_gate,
            preferred_shell=self._preferred_shell,
        )

    def with_safety_policy(
        self,
        safety_policy: RuntimeSafetyPolicy,
        *,
        on_audit: AuditCallback = None,
        on_tool_event: ToolEventCallback = None,
    ) -> "ToolExecutor":
        return ToolExecutor(
            dict(self._tools),
            confirm_command=self._confirm_command,
            on_info=self._on_info,
            safety_policy=safety_policy,
            on_audit=self._on_audit if on_audit is None else on_audit,
            on_tool_event=self._on_tool_event if on_tool_event is None else on_tool_event,
            execution_gate=self._execution_gate,
            preferred_shell=self._preferred_shell,
        )

    def with_shell_preference(self, preferred_shell: str | None) -> "ToolExecutor":
        return ToolExecutor(
            dict(self._tools),
            confirm_command=self._confirm_command,
            on_info=self._on_info,
            safety_policy=self._safety_policy,
            on_audit=self._on_audit,
            on_tool_event=self._on_tool_event,
            execution_gate=self._execution_gate,
            preferred_shell=preferred_shell,
        )

    def with_execution_gate(self, execution_gate: ToolExecutionGate) -> "ToolExecutor":
        return ToolExecutor(
            dict(self._tools),
            confirm_command=self._confirm_command,
            on_info=self._on_info,
            safety_policy=self._safety_policy,
            on_audit=self._on_audit,
            on_tool_event=self._on_tool_event,
            execution_gate=execution_gate,
            preferred_shell=self._preferred_shell,
        )

    def execute(self, tool_name: str, args: dict) -> str:
        effective_args = self._apply_runtime_args(tool_name, args)
        capability = self._resolve_capability(tool_name)
        target_path = self._resolve_target_path(effective_args)
        target = self._summarize_target(tool_name, effective_args, target_path)
        args_summary = self._summarize_args(effective_args)
        context = _ExecutionContext(
            tool_name=tool_name,
            capability=capability,
            target=target,
            args_summary=args_summary,
        )
        input_payload = self._build_input_payload(effective_args)

        # Emit the invocation before policy checks so blocked attempts still show
        # up in the execution trail alongside their audit events.
        self._emit_tool_event(
            event_type="tool_invoked",
            tool_name=tool_name,
            capability=capability,
            args_summary=args_summary,
            target=target,
            input_payload=input_payload,
        )

        gate_decision = self._apply_execution_gate(
            context=context,
            effective_args=effective_args,
        )
        if gate_decision is not None and not gate_decision.is_allowed:
            self._emit_tool_event(
                event_type="tool_failed",
                tool_name=tool_name,
                capability=capability,
                args_summary=args_summary,
                error=gate_decision.message,
                target=target,
                input_payload=input_payload,
                output_payload={"error": gate_decision.message},
            )
            raise ToolExecutionBlockedError(
                tool_name,
                capability,
                gate_decision.message,
                reason=gate_decision.reason,
            )

        tool = self._tools.get(tool_name)
        if tool is None:
            error = f"Unknown tool requested: {tool_name}"
            self._emit_tool_event(
                event_type="tool_failed",
                tool_name=tool_name,
                capability=capability,
                args_summary=args_summary,
                error=error,
                target=target,
                input_payload=input_payload,
                output_payload={"error": error},
            )
            self._emit_audit(
                event_type="operation_failed",
                tool_name=tool_name,
                capability=capability,
                reason="unknown_tool",
                target=target,
            )
            raise ToolExecutionError(tool_name, capability, error)

        denial = self._enforce_policy(context)
        if denial is not None:
            self._emit_tool_event(
                event_type="tool_failed",
                tool_name=tool_name,
                capability=capability,
                args_summary=args_summary,
                error=denial,
                target=target,
                input_payload=input_payload,
                output_payload={"error": denial},
            )
            return denial

        self._warn_sensitive_read(target_path, capability)

        # Reads only generate warnings. Everything that mutates state or executes
        # code goes through confirmation or shell-risk checks first.
        if capability == CapabilityTier.WRITE and self._is_sensitive_target(target_path):
            denial = self._require_confirmation(
                context,
                reason="sensitive_write_path",
                prompt_text=f"Allow write tool '{tool_name}' to modify sensitive path '{target}'?",
            )
            if denial is not None:
                self._emit_tool_event(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    capability=capability,
                    args_summary=args_summary,
                    error=denial,
                    target=target,
                    input_payload=input_payload,
                    output_payload={"error": denial},
                )
                return denial

        if capability == CapabilityTier.DESTRUCTIVE:
            denial = self._require_confirmation(
                context,
                reason="destructive_tool",
                prompt_text=f"Allow destructive tool '{tool_name}' on '{target}'?",
            )
            if denial is not None:
                self._emit_tool_event(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    capability=capability,
                    args_summary=args_summary,
                    error=denial,
                    target=target,
                    input_payload=input_payload,
                    output_payload={"error": denial},
                )
                return denial

        if capability == CapabilityTier.EXECUTE:
            denial = self._handle_shell_safety(context, effective_args.get("command", ""))
            if denial is not None:
                self._emit_tool_event(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    capability=capability,
                    args_summary=args_summary,
                    error=denial,
                    target=target,
                    input_payload=input_payload,
                    output_payload={"error": denial},
                )
                return denial

        try:
            envelope = self._execute_registered_tool(tool, effective_args)
            result = envelope.to_model_text()
            recoverable_error = self._extract_recoverable_tool_error(result)
            if recoverable_error is not None:
                self._emit_tool_event(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    capability=capability,
                    args_summary=args_summary,
                    error=recoverable_error,
                    target=target,
                    input_payload=input_payload,
                    output_payload={"error": recoverable_error},
                )
                return recoverable_error
            output_payload = envelope.to_event_payload()
            self._emit_tool_event(
                event_type="tool_completed",
                tool_name=tool_name,
                capability=capability,
                args_summary=args_summary,
                result_summary=envelope.summary,
                target=target,
                input_payload=input_payload,
                output_payload=output_payload,
            )
            return result
        except Exception as exc:
            error = str(exc)
            self._emit_tool_event(
                event_type="tool_failed",
                tool_name=tool_name,
                capability=capability,
                args_summary=args_summary,
                error=error,
                target=target,
                input_payload=input_payload,
                output_payload={"error": error},
            )
            if capability != CapabilityTier.READ:
                self._emit_audit(
                    event_type="operation_failed",
                    tool_name=tool_name,
                    capability=capability,
                    reason="tool_execution_error",
                    target=target,
                )
            raise ToolExecutionError(tool_name, capability, error) from exc

    def _enforce_policy(self, context: _ExecutionContext) -> str | None:
        if self._safety_policy.allows(context.capability):
            return None

        reason = "capability_not_permitted"
        self._emit_audit(
            event_type="policy_denied",
            tool_name=context.tool_name,
            capability=context.capability,
            reason=reason,
            target=context.target,
        )
        return (
            f"Blocked {context.tool_name}: capability '{context.capability.value}' "
            "is not allowed in the current runtime."
        )

    def _warn_sensitive_read(self, target_path: Path | None, capability: CapabilityTier) -> None:
        if capability == CapabilityTier.READ and self._is_sensitive_target(target_path) and self._on_info:
            self._on_info(f"Sensitive path access: {target_path.as_posix()}")

    def _handle_shell_safety(self, context: _ExecutionContext, command: str) -> str | None:
        safety_level = detect_danger(command)
        if safety_level == "BLOCK":
            self._emit_audit(
                event_type="operation_blocked",
                tool_name=context.tool_name,
                capability=context.capability,
                reason="shell_policy_block",
                target=command,
                command_risk=safety_level,
            )
            return f"Blocked shell command: classified as high risk.\nCommand: {command}"

        if safety_level == "CONFIRM":
            return self._require_confirmation(
                context,
                reason="shell_command_requires_confirmation",
                prompt_text=f"Allow shell command?\n{command}",
                command_risk=safety_level,
                target=command,
            )

        return None

    def _require_confirmation(
        self,
        context: _ExecutionContext,
        *,
        reason: str,
        prompt_text: str,
        command_risk: str | None = None,
        target: str | None = None,
    ) -> str | None:
        effective_target = target or context.target
        self._emit_audit(
            event_type="confirmation_required",
            tool_name=context.tool_name,
            capability=context.capability,
            reason=reason,
            target=effective_target,
            command_risk=command_risk,
        )

        if self._on_info:
            detail = effective_target or context.tool_name
            self._on_info(
                f"Confirmation required for {context.capability.value} tool "
                f"'{context.tool_name}' on {detail}."
            )

        if self._confirm_command is None:
            self._emit_audit(
                event_type="operation_blocked",
                tool_name=context.tool_name,
                capability=context.capability,
                reason="confirmation_unavailable",
                target=effective_target,
                command_risk=command_risk,
            )
            return (
                f"Blocked {context.tool_name}: confirmation is required for this "
                f"{context.capability.value} operation but no confirmation handler is available."
            )

        if not self._confirm_command(prompt_text):
            self._emit_audit(
                event_type="operation_blocked",
                tool_name=context.tool_name,
                capability=context.capability,
                reason="user_declined_confirmation",
                target=effective_target,
                command_risk=command_risk,
            )
            return f"Blocked {context.tool_name}: user declined confirmation."

        self._emit_audit(
            event_type="operation_confirmed",
            tool_name=context.tool_name,
            capability=context.capability,
            reason=reason,
            target=effective_target,
            command_risk=command_risk,
        )
        return None

    def _resolve_target_path(self, args: dict) -> Path | None:
        for key in ("file_path", "path"):
            raw_path = args.get(key)
            if not raw_path or not isinstance(raw_path, str):
                continue
            try:
                # Invalid or out-of-workspace paths are left as opaque targets so
                # later checks can report a clear user-facing denial.
                return resolve_safe_path(raw_path)
            except ValueError:
                return None
        return None

    def _resolve_capability(self, tool_name: str) -> CapabilityTier:
        try:
            return get_tool_capability(tool_name)
        except ValueError:
            return CapabilityTier.READ

    def _summarize_target(self, tool_name: str, args: dict, target_path: Path | None) -> str | None:
        if target_path is not None:
            return target_path.as_posix()
        if tool_name == "bash":
            command = args.get("command", "")
            return command[:200]
        return None

    def _apply_runtime_args(self, tool_name: str, args: dict) -> dict:
        effective_args = dict(args)
        if tool_name == "bash" and self._preferred_shell and not effective_args.get("shell"):
            effective_args["shell"] = self._preferred_shell
        return effective_args

    def _summarize_args(self, args: dict) -> str:
        compact: dict[str, object] = {}
        for key, value in sorted(args.items()):
            if isinstance(value, str):
                compact[key] = value[:120] + ("..." if len(value) > 120 else "")
            else:
                compact[key] = value
        return self._truncate(json.dumps(compact, ensure_ascii=False, sort_keys=True), limit=200)

    def _summarize_result(self, result: object) -> str:
        text = str(result)
        first_line = text.splitlines()[0] if text else ""
        return self._truncate(first_line or text, limit=200)

    def _is_sensitive_target(self, target_path: Path | None) -> bool:
        return target_path is not None and is_sensitive_path(target_path.as_posix())

    def _emit_audit(
        self,
        *,
        event_type: str,
        tool_name: str,
        capability: CapabilityTier,
        reason: str,
        target: str | None = None,
        command_risk: str | None = None,
    ) -> None:
        if self._on_audit is None:
            return
        self._on_audit(
            SafetyAuditEvent(
                event_type=event_type,
                tool_name=tool_name,
                capability=capability,
                reason=reason,
                target=target,
                command_risk=command_risk,
            )
        )

    def _emit_tool_event(
        self,
        *,
        event_type: str,
        tool_name: str,
        capability: CapabilityTier,
        args_summary: str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
        target: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
    ) -> None:
        if self._on_tool_event is None:
            return
        self._on_tool_event(
            ToolExecutionEvent(
                event_type=event_type,
                tool_name=tool_name,
                capability=capability,
                args_summary=args_summary,
                result_summary=result_summary,
                error=error,
                target=target,
                input_payload=dict(input_payload or {}),
                output_payload=dict(output_payload or {}),
            )
        )

    def _truncate(self, value: str, *, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    def _build_input_payload(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._compact_payload(args, limit=500)

    def _build_output_payload(self, result: object) -> dict[str, Any]:
        if isinstance(result, SecurityToolResult):
            return {
                "summary": result.summary,
                "target": result.target,
                "payload": self._compact_payload(result.payload, limit=2000),
                "artifact_count": len(result.evidence_candidates),
                "finding_count": len(result.finding_candidates),
            }
        if isinstance(result, ToolResultEnvelope):
            return result.to_event_payload()
        text = str(result)
        structured = self._extract_json_tail(text)
        if structured is not None:
            return self._compact_payload(structured, limit=2000)
        return {"text": self._truncate(text, limit=2000)}

    def _execute_registered_tool(self, tool: object, args: dict[str, Any]) -> ToolResultEnvelope:
        if isinstance(tool, ToolDefinition):
            return tool.run(args)
        result = tool.invoke(args)
        if isinstance(result, ToolResultEnvelope):
            return result
        return ToolResultEnvelope(
            summary=self._summarize_result(result),
            model_text=str(result),
            data=self._build_output_payload(str(result)),
        )

    def _extract_json_tail(self, text: str) -> dict[str, Any] | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in reversed(lines[-3:]):
            if not line.startswith("{"):
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
        return None

    def _compact_payload(self, value: Any, *, limit: int) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._compact_payload(item, limit=limit)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._compact_payload(item, limit=limit) for item in value]
        if isinstance(value, str):
            return self._truncate(value, limit=limit)
        return value

    def _extract_recoverable_tool_error(self, result: object) -> str | None:
        if not isinstance(result, str):
            return None
        if not result.startswith(RECOVERABLE_TOOL_ERROR_PREFIX):
            return None
        return result.removeprefix(RECOVERABLE_TOOL_ERROR_PREFIX).strip() or "Error"

    def _apply_execution_gate(
        self,
        *,
        context: _ExecutionContext,
        effective_args: dict[str, Any],
    ) -> ToolExecutionGateDecision | None:
        if self._execution_gate is None:
            return None
        request = ToolExecutionRequest(
            tool_name=context.tool_name,
            capability=context.capability,
            args=dict(effective_args),
            target=context.target,
            args_summary=context.args_summary,
        )
        return self._execution_gate(request)


class SecurityToolExecutor:
    def __init__(self, tools: dict[str, SecurityTool]) -> None:
        self._tools = dict(tools)

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)

    def get_tool(self, tool_name: str) -> SecurityTool:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise SecurityToolExecutionError(tool_name, f"Unknown security tool requested: {tool_name}")
        return tool

    def validate(
        self,
        tool_name: str,
        *,
        target: str,
        arguments: dict[str, Any],
        policy: ScopePolicy,
    ) -> SecurityToolInvocation:
        tool = self.get_tool(tool_name)
        try:
            return tool.validate_invocation(target=target, arguments=arguments, policy=policy)
        except Exception as exc:
            raise SecurityToolExecutionError(tool_name, str(exc)) from exc

    def execute(
        self,
        tool_name: str,
        *,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult:
        tool = self.get_tool(tool_name)
        try:
            return tool.execute(invocation, target)
        except Exception as exc:
            raise SecurityToolExecutionError(tool_name, str(exc)) from exc
