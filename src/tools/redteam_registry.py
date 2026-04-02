from __future__ import annotations

from tools.contracts import TypedSecurityTool


class RedTeamToolRegistry:
    def __init__(self, tools: list[TypedSecurityTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def get(self, tool_name: str) -> TypedSecurityTool:
        try:
            return self._tools[tool_name]
        except KeyError as exc:
            raise ValueError(f"Unknown red-team tool: {tool_name}") from exc

    def names(self) -> set[str]:
        return set(self._tools)


def build_red_team_registry(tools: list[TypedSecurityTool]) -> RedTeamToolRegistry:
    return RedTeamToolRegistry(tools)
