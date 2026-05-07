from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from agent.settings import get_settings
from models.run import utc_now_iso
from runtime.ctf_agent_tasks import CTFAgentTaskRuntime
from runtime.scanner_tasks import ScannerTaskRuntime

from .dependencies import AppRuntimeState


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    scanner_tasks = ScannerTaskRuntime(settings=settings)
    ctf_agent_tasks = CTFAgentTaskRuntime(settings=settings)
    app.state.runtime_state = AppRuntimeState(
        settings=settings,
        started_at=utc_now_iso(),
        scanner_tasks=scanner_tasks,
        ctf_agent_tasks=ctf_agent_tasks,
    )
    try:
        yield
    finally:
        ctf_agent_tasks.shutdown()
        scanner_tasks.shutdown()
