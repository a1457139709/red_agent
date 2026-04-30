from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .contracts import SecurityTool


class InvokableFunction:
    def __init__(self, func: Callable[..., str]) -> None:
        self.func = func
        self.name = func.__name__
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return self.func(*args, **kwargs)

    def invoke(self, args: dict[str, Any]) -> str:
        return self.func(**dict(args))


def invokable(func: Callable[..., str]) -> InvokableFunction:
    return InvokableFunction(func)


def build_security_registry(
    tools: Iterable[SecurityTool],
    allowed_names: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, SecurityTool]:
    allowed = None if allowed_names is None else set(allowed_names)
    return {
        tool.name: tool
        for tool in tools
        if allowed is None or tool.name in allowed
    }
