from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.terminal_service import TerminalDescriptor
from models.control_center import CommandRun
from server.dependencies import AppRuntimeState, get_runtime_state
from server.routes.workspace import serialize_evidence

router = APIRouter(prefix="/api", tags=["terminal"])


class TerminalOpenRequest(BaseModel):
    rows: int = Field(default=24, ge=1)
    cols: int = Field(default=80, ge=1)


class CommandEvidenceRequest(BaseModel):
    title: str = Field(min_length=1)
    selected_text: str = Field(min_length=1)
    summary: str | None = None
    attack_path_node_id: str | None = None
    tags: list[str] = Field(default_factory=list)


def serialize_terminal(terminal: TerminalDescriptor) -> dict[str, Any]:
    return {
        "terminal_id": terminal.terminal_id,
        "project_id": terminal.project_id,
        "session_id": terminal.session_id,
        "working_directory": terminal.working_directory,
        "status": terminal.status,
        "created_at": terminal.created_at,
    }


def serialize_command_run(command: CommandRun) -> dict[str, Any]:
    return {
        "id": command.id,
        "public_id": command.public_id,
        "project_id": command.project_id,
        "session_id": command.session_id,
        "terminal_id": command.terminal_id,
        "command": command.command,
        "exit_code": command.exit_code,
        "output_ref": command.output_ref,
        "output_summary": command.output_summary,
        "working_directory": command.working_directory,
        "tags": list(command.tags),
        "started_at": command.started_at,
        "ended_at": command.ended_at,
        "created_at": command.created_at,
    }


@router.post("/sessions/{session_id}/terminals", status_code=201)
async def open_session_terminal(
    session_id: str,
    request: TerminalOpenRequest,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        terminal = runtime_state.terminal_service.open_terminal(
            session_identifier=session_id,
            rows=request.rows,
            cols=request.cols,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"terminal": serialize_terminal(terminal)}


@router.get("/terminals/{terminal_id}/commands")
async def list_terminal_commands(
    terminal_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, list[dict[str, Any]]]:
    commands = runtime_state.terminal_service.list_commands(terminal_identifier=terminal_id, limit=None)
    return {"commands": [serialize_command_run(command) for command in commands]}


@router.post("/commands/{command_run_id}/evidence", status_code=201)
async def create_command_evidence(
    command_run_id: str,
    request: CommandEvidenceRequest,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        evidence = runtime_state.terminal_service.create_evidence_from_command(
            command_identifier=command_run_id,
            title=request.title,
            selected_text=request.selected_text,
            summary=request.summary,
            attack_path_node_id=request.attack_path_node_id,
            tags=request.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"evidence": serialize_evidence(evidence)}
