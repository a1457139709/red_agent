from __future__ import annotations

from importlib import import_module

__all__ = ["RunRepository", "SQLiteStorage", "TaskRepository"]

_EXPORTS = {
    "RunRepository": ".runs",
    "SQLiteStorage": ".sqlite",
    "TaskRepository": ".tasks",
}


def __getattr__(name: str) -> object:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
