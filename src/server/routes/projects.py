from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.project_service import ProjectService
from app.target_session_service import TargetSessionService
from models.control_center import (
    Project,
    ProjectDashboard,
    ProjectStatus,
    SessionDashboard,
    TargetSession,
    TargetSessionStatus,
    TargetType,
)

router = APIRouter(prefix="/api", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class ProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProjectStatus | None = None


class TargetSessionCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    target_value: str = Field(min_length=1)
    target_type: TargetType
    summary: str | None = None


class TargetSessionPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    target_value: str | None = Field(default=None, min_length=1)
    target_type: TargetType | None = None
    summary: str | None = None
    status: TargetSessionStatus | None = None


def serialize_project(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "public_id": project.public_id,
        "name": project.name,
        "description": project.description,
        "root_path": project.root_path,
        "status": project.status.value,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "metadata": dict(project.metadata),
    }


def serialize_target_session(session: TargetSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "public_id": session.public_id,
        "project_id": session.project_id,
        "name": session.name,
        "target_value": session.target_value,
        "target_type": session.target_type.value,
        "status": session.status.value,
        "summary": session.summary,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "metadata": dict(session.metadata),
    }


def serialize_dashboard(dashboard: SessionDashboard) -> dict[str, Any]:
    return {
        "project": serialize_project(dashboard.project),
        "session": serialize_target_session(dashboard.session),
        "target": {
            "value": dashboard.session.target_value,
            "type": dashboard.session.target_type.value,
            "summary": dashboard.session.summary,
        },
        "task_counts": dict(dashboard.task_counts),
        "finding_counts": dict(dashboard.finding_counts),
        "evidence_count": dashboard.evidence_count,
        "flag_count": dashboard.flag_count,
        "open_ports": list(dashboard.open_ports),
        "web_entries": list(dashboard.web_entries),
        "directory_findings": list(dashboard.directory_findings),
        "poc_hits": list(dashboard.poc_hits),
        "attack_path": list(dashboard.attack_path),
        "recent_commands": list(dashboard.recent_commands),
        "evidence": list(dashboard.evidence),
        "flags": list(dashboard.flags),
        "next_actions": list(dashboard.next_actions),
    }


def serialize_project_dashboard(dashboard: ProjectDashboard) -> dict[str, Any]:
    return {
        "project": serialize_project(dashboard.project),
        "sessions": [serialize_target_session(session) for session in dashboard.sessions],
        "session_count": len(dashboard.sessions),
        "session_counts": dict(dashboard.session_counts),
        "task_counts": dict(dashboard.task_counts),
        "finding_counts": dict(dashboard.finding_counts),
        "running_task_count": dashboard.running_task_count,
        "open_service_count": dashboard.open_service_count,
        "finding_count": dashboard.finding_count,
        "flag_count": dashboard.flag_count,
        "recent_activity": list(dashboard.recent_activity),
    }


@router.get("/projects")
async def list_projects() -> dict[str, list[dict[str, Any]]]:
    projects = ProjectService.from_settings().list_projects(limit=None)
    return {"projects": [serialize_project(project) for project in projects]}


@router.post("/projects", status_code=201)
async def create_project(request: ProjectCreateRequest) -> dict[str, Any]:
    try:
        project = ProjectService.from_settings().create_project(
            name=request.name,
            description=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"project": serialize_project(project)}


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    project = ProjectService.from_settings().get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return {"project": serialize_project(project)}


@router.patch("/projects/{project_id}")
async def patch_project(project_id: str, request: ProjectPatchRequest) -> dict[str, Any]:
    changes = request.model_dump(exclude_unset=True)
    try:
        project = ProjectService.from_settings().update_project(
            project_id,
            name=changes.get("name"),
            description=changes.get("description"),
            status=changes.get("status"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"project": serialize_project(project)}


@router.get("/projects/{project_id}/dashboard")
async def get_project_dashboard(project_id: str) -> dict[str, Any]:
    try:
        dashboard = ProjectService.from_settings().build_dashboard(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"dashboard": serialize_project_dashboard(dashboard)}


@router.get("/projects/{project_id}/sessions")
async def list_project_sessions(project_id: str) -> dict[str, list[dict[str, Any]]]:
    try:
        sessions = TargetSessionService.from_settings().list_sessions(
            project_identifier=project_id,
            limit=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"sessions": [serialize_target_session(session) for session in sessions]}


@router.post("/projects/{project_id}/sessions", status_code=201)
async def create_project_session(
    project_id: str,
    request: TargetSessionCreateRequest,
) -> dict[str, Any]:
    try:
        session = TargetSessionService.from_settings().create_session(
            project_identifier=project_id,
            name=request.name,
            target_value=request.target_value,
            target_type=request.target_type,
            summary=request.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": serialize_target_session(session)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = TargetSessionService.from_settings().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Target session not found: {session_id}")
    return {"session": serialize_target_session(session)}


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, request: TargetSessionPatchRequest) -> dict[str, Any]:
    changes = request.model_dump(exclude_unset=True)
    try:
        session = TargetSessionService.from_settings().update_session(
            session_id,
            name=changes.get("name"),
            target_value=changes.get("target_value"),
            target_type=changes.get("target_type"),
            summary=changes.get("summary"),
            status=changes.get("status"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": serialize_target_session(session)}


@router.get("/sessions/{session_id}/dashboard")
async def get_session_dashboard(session_id: str) -> dict[str, Any]:
    try:
        dashboard = TargetSessionService.from_settings().build_dashboard(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"dashboard": serialize_dashboard(dashboard)}
