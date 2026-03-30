from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tools.policy import CapabilityTier, RuntimeSafetyPolicy, SafetyAuditEvent, get_tool_capability
from utils.safety import detect_danger, is_sensitive_path, resolve_safe_path


AuditCallback = Callable[[SafetyAuditEvent], None] | None
ConfirmCallback = Callable[[str], bool] | None
InfoCallback = Callable[[str], None] | None


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    tool_name: str
    capability: CapabilityTier
    target: str | None = None


class ToolExecutor:
    def __init__(
        self,
        tools: dict,
        *,
        confirm_command: ConfirmCallback = None,
        on_info: InfoCallback = None,
        safety_policy: RuntimeSafetyPolicy | None = None,
        on_audit: AuditCallback = None,
    ) -> None:
        self._tools = tools
        self._confirm_command = confirm_command
        self._on_info = on_info
        self._safety_policy = safety_policy or RuntimeSafetyPolicy.base()
        self._on_audit = on_audit

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)

    @property
    def safety_policy(self) -> RuntimeSafetyPolicy:
        return self._safety_policy

    def get_tools(self) -> list:
        return list(self._tools.values())

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
        )

    def with_safety_policy(
        self,
        safety_policy: RuntimeSafetyPolicy,
        *,
        on_audit: AuditCallback = None,
    ) -> "ToolExecutor":
        return ToolExecutor(
            dict(self._tools),
            confirm_command=self._confirm_command,
            on_info=self._on_info,
            safety_policy=safety_policy,
            on_audit=self._on_audit if on_audit is None else on_audit,
        )

    def execute(self, tool_name: str, args: dict) -> str:
        tool = self._tools[tool_name]
        try:
            capability = get_tool_capability(tool_name)
        except ValueError:
            capability = CapabilityTier.READ
        target_path = self._resolve_target_path(args)
        target = self._summarize_target(tool_name, args, target_path)
        context = _ExecutionContext(
            tool_name=tool_name,
            capability=capability,
            target=target,
        )

        denial = self._enforce_policy(context)
        if denial is not None:
            return denial

        self._warn_sensitive_read(target_path, capability)

        if capability == CapabilityTier.WRITE and self._is_sensitive_target(target_path):
            denial = self._require_confirmation(
                context,
                reason="sensitive_write_path",
                prompt_text=f"Allow write tool '{tool_name}' to modify sensitive path '{target}'?",
            )
            if denial is not None:
                return denial

        if capability == CapabilityTier.DESTRUCTIVE:
            denial = self._require_confirmation(
                context,
                reason="destructive_tool",
                prompt_text=f"Allow destructive tool '{tool_name}' on '{target}'?",
            )
            if denial is not None:
                return denial

        if capability == CapabilityTier.EXECUTE:
            denial = self._handle_shell_safety(context, args.get("command", ""))
            if denial is not None:
                return denial

        try:
            return tool.invoke(args)
        except Exception:
            if capability != CapabilityTier.READ:
                self._emit_audit(
                    event_type="operation_failed",
                    tool_name=tool_name,
                    capability=capability,
                    reason="tool_execution_error",
                    target=target,
                )
            raise

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
            return f"Blocked shell command (拒绝执行): classified as high risk.\nCommand: {command}"

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
                f"Blocked {context.tool_name} (拒绝执行): confirmation is required for this "
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
            return f"Blocked {context.tool_name}: user declined confirmation. (用户拒绝)"

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
                return resolve_safe_path(raw_path)
            except ValueError:
                return None
        return None

    def _summarize_target(self, tool_name: str, args: dict, target_path: Path | None) -> str | None:
        if target_path is not None:
            return target_path.as_posix()
        if tool_name == "bash":
            command = args.get("command", "")
            return command[:200]
        return None

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
