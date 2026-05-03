from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from agent.settings import get_settings
from models.run import utc_now_iso

from .dependencies import AppRuntimeState


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.runtime_state = AppRuntimeState(
        settings=get_settings(),
        started_at=utc_now_iso(),
    )
    yield
