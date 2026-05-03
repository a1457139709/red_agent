from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from server.dependencies import AppRuntimeState, get_runtime_state

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(
    runtime_state: Annotated[AppRuntimeState, Depends(get_runtime_state)],
) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "control-center",
        "started_at": runtime_state.started_at,
    }
