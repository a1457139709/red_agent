from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from agent.settings import Settings
from runtime.ctf_agent_tasks import CTFAgentTaskRuntime
from runtime.scanner_tasks import ScannerTaskRuntime


@dataclass(frozen=True, slots=True)
class AppRuntimeState:
    settings: Settings
    started_at: str
    scanner_tasks: ScannerTaskRuntime
    ctf_agent_tasks: CTFAgentTaskRuntime


def get_runtime_state(request: Request) -> AppRuntimeState:
    state = getattr(request.app.state, "runtime_state", None)
    if state is None:
        raise RuntimeError("App runtime state is not initialized.")
    return state
