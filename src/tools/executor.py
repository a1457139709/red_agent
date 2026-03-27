from collections.abc import Callable

from utils.safety import detect_danger, is_sensitive_path, resolve_safe_path


class ToolExecutor:
    def __init__(
        self,
        tools: dict,
        *,
        confirm_command: Callable[[str], bool] | None = None,
        on_info: Callable[[str], None] | None = None,
    ) -> None:
        self._tools = tools
        self._confirm_command = confirm_command
        self._on_info = on_info

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)
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
        )

    def execute(self, tool_name: str, args: dict) -> str:
        tool = self._tools[tool_name]
        self._warn_sensitive_path(args)

        if tool_name == "bash":
            command = args.get("command", "")
            blocked = self._handle_shell_safety(command)
            if blocked is not None:
                return blocked

        return tool.invoke(args)

    def _warn_sensitive_path(self, args: dict) -> None:
        for key in ("file_path", "path"):
            raw_path = args.get(key)
            if not raw_path or not isinstance(raw_path, str):
                continue

            try:
                safe_path = resolve_safe_path(raw_path)
            except ValueError:
                return

            if is_sensitive_path(safe_path.as_posix()) and self._on_info:
                self._on_info(f"正在访问敏感路径：{safe_path.as_posix()}")
            return

    def _handle_shell_safety(self, command: str) -> str | None:
        safety_level = detect_danger(command)
        if safety_level == "BLOCK":
            return f"拒绝执行：该命令已被自动阻止（高风险操作）。\n命令：${command}"

        if safety_level == "CONFIRM":
            if self._on_info:
                self._on_info(f"警告：该命令可能具有潜在风险，请确认后再执行。\n命令：${command}")

            if self._confirm_command is None:
                return f"拒绝执行：该命令需要用户确认，但当前执行环境未提供确认能力。\n命令：${command}"

            if not self._confirm_command(command):
                return f"该命令已被用户拒绝（潜在风险）。\n命令：${command}"

        return None
