from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ctf_agent_service import CTFAgentService
from server.dependencies import AppRuntimeState, get_runtime_state
from server.routes.tasks import serialize_task

router = APIRouter(prefix="/api", tags=["agent"])


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=1)


@router.post("/sessions/{session_id}/agent/messages", status_code=202)
async def create_agent_message(
    session_id: str,
    request: AgentMessageRequest,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        task = CTFAgentService.from_settings(runtime_state.settings).create_agent_task(
            session_identifier=session_id,
            message=request.message,
        )
        runtime_state.ctf_agent_tasks.submit(task.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"task": serialize_task(task)}
