from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.session import SessionMode


class ToolAccessDecisionStatus:
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ToolAccessDecision:
    status: str
    reason: str
    message: str

    @property
    def requires_confirmation(self) -> bool:
        return self.status == ToolAccessDecisionStatus.CONFIRM

    @property
    def is_denied(self) -> bool:
        return self.status == ToolAccessDecisionStatus.DENY


class ToolAccessPolicyService:
    READ_ONLY_TOOLS = frozenset({"list_dir", "read_file", "search", "web_fetch", "web_search"})
    WRITE_TOOLS = frozenset({"write_file", "edit_file"})
    DESTRUCTIVE_TOOLS = frozenset({"delete_file"})
    BLOCKED_IN_REDTEAM = frozenset({"bash"})

    def evaluate_tool_access(
        self,
        *,
        mode: SessionMode,
        tool_name: str,
        arguments: dict[str, Any] | None,
        workspace: str,
        session_public_id: str,
    ) -> ToolAccessDecision:
        if mode != SessionMode.REDTEAM:
            return ToolAccessDecision(
                status=ToolAccessDecisionStatus.ALLOW,
                reason="normal_mode",
                message="Normal mode base policy allows this tool.",
            )

        if tool_name in self.BLOCKED_IN_REDTEAM:
            return ToolAccessDecision(
                status=ToolAccessDecisionStatus.DENY,
                reason="shell_bypass_blocked",
                message="Redteam mode blocks raw shell execution by default.",
            )

        if tool_name in self.READ_ONLY_TOOLS:
            return ToolAccessDecision(
                status=ToolAccessDecisionStatus.ALLOW,
                reason="redteam_read_only",
                message="Read-only tool is allowed in redteam mode.",
            )

        if tool_name in self.DESTRUCTIVE_TOOLS:
            return ToolAccessDecision(
                status=ToolAccessDecisionStatus.CONFIRM,
                reason="redteam_destructive_requires_confirmation",
                message="Destructive file operations require confirmation in redteam mode.",
            )

        if tool_name in self.WRITE_TOOLS:
            if self._is_session_owned_path(
                workspace=workspace,
                session_public_id=session_public_id,
                arguments=arguments or {},
            ):
                return ToolAccessDecision(
                    status=ToolAccessDecisionStatus.ALLOW,
                    reason="session_owned_output",
                    message="Write is inside the session-owned output area.",
                )
            return ToolAccessDecision(
                status=ToolAccessDecisionStatus.CONFIRM,
                reason="write_outside_session_area_requires_confirmation",
                message="Write outside the session-owned output area requires confirmation.",
            )

        return ToolAccessDecision(
            status=ToolAccessDecisionStatus.ALLOW,
            reason="unscoped_tool",
            message="Tool is not restricted by redteam base access policy.",
        )

    def _is_session_owned_path(
        self,
        *,
        workspace: str,
        session_public_id: str,
        arguments: dict[str, Any],
    ) -> bool:
        path_arg = self._extract_path_arg(arguments)
        if path_arg is None:
            return False

        workspace_path = Path(workspace).resolve()
        candidate_path = self._resolve_path(workspace_path, path_arg)
        session_output_root = (
            workspace_path / ".red-code" / "sessions" / session_public_id
        ).resolve()
        return self._is_relative_to(candidate_path, session_output_root)

    def _extract_path_arg(self, arguments: dict[str, Any]) -> str | None:
        for key in ("path", "file_path", "target_path"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _resolve_path(self, workspace_path: Path, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        return candidate.resolve()

    def _is_relative_to(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True
