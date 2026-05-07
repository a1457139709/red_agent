from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.scanner_service import ScannerService
from models.control_center import Task
from server.dependencies import AppRuntimeState, get_runtime_state

router = APIRouter(prefix="/api", tags=["tasks"])


class TaskCreateRequest(BaseModel):
    task_type: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


def serialize_task(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "public_id": task.public_id,
        "project_id": task.project_id,
        "session_id": task.session_id,
        "task_type": task.task_type,
        "executor": task.executor,
        "status": task.status.value,
        "input": dict(task.input_json),
        "result": dict(task.result_json),
        "started_at": task.started_at,
        "ended_at": task.ended_at,
        "error": task.error,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@router.post("/sessions/{session_id}/tasks", status_code=201)
async def create_session_task(
    session_id: str,
    request: TaskCreateRequest,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        task = ScannerService.from_settings(runtime_state.settings).enqueue_scan_task(
            session_identifier=session_id,
            task_type=request.task_type,
            input_data=request.input,
        )
        runtime_state.scanner_tasks.submit(task.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"task": serialize_task(task)}


@router.get("/sessions/{session_id}/tasks")
async def list_session_tasks(
    session_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, list[dict[str, Any]]]:
    try:
        tasks = ScannerService.from_settings(runtime_state.settings).list_tasks(
            session_identifier=session_id,
            limit=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"tasks": [serialize_task(task) for task in tasks]}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        task = ScannerService.from_settings(runtime_state.settings).cancel_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"task": serialize_task(task)}


@router.post("/tasks/{task_id}/rerun", status_code=201)
async def rerun_task(
    task_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        task = ScannerService.from_settings(runtime_state.settings).enqueue_rerun_task(task_id)
        runtime_state.scanner_tasks.submit(task.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"task": serialize_task(task)}
