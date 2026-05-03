from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from agent.settings import Settings


@dataclass(frozen=True, slots=True)
class AppRuntimeState:
    settings: Settings
    started_at: str


def get_runtime_state(request: Request) -> AppRuntimeState:
    state = getattr(request.app.state, "runtime_state", None)
    if state is None:
        raise RuntimeError("App runtime state is not initialized.")
    return state
