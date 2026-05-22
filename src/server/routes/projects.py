from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.project_service import ProjectService
from app.target_admission_service import TargetAdmissionService
from app.target_session_service import TargetSessionService
from models.control_center import (
    CampaignTarget,
    Project,
    ProjectDashboard,
    ProjectStatus,
    SessionDashboard,
    TargetPoolStatus,
    TargetSource,
    TargetSession,
    TargetSessionStatus,
    TargetType,
)
from models.scope_policy import ScopePolicy

router = APIRouter(prefix="/api", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class ProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProjectStatus | None = None


class TargetSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    summary: str | None = None


class TargetSessionPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    status: TargetSessionStatus | None = None


class ScopePolicyPatchRequest(BaseModel):
    allowed_hosts: list[str] | None = None
    allowed_domains: list[str] | None = None
    allowed_cidrs: list[str] | None = None
    allowed_ports: list[int] | None = None
    allowed_protocols: list[str] | None = None
    denied_targets: list[str] | None = None
    allowed_tool_categories: list[str] | None = None
    confirmation_required_actions: list[str] | None = None


class TargetProposalRequest(BaseModel):
    value: str = Field(min_length=1)
    source: TargetSource = TargetSource.AGENT_DISCOVERED
    evidence_id: str | None = None
    discovered_by: str | None = None
    discovered_from: str | None = None


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
        "status": session.status.value,
        "summary": session.summary,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "metadata": dict(session.metadata),
    }


def serialize_target(target: CampaignTarget) -> dict[str, Any]:
    return {
        "id": target.id,
        "public_id": target.public_id,
        "project_id": target.project_id,
        "value": target.value,
        "target_type": target.target_type.value,
        "normalized_host": target.normalized_host,
        "source": target.source.value,
        "status": target.status.value,
        "confidence": target.confidence,
        "discovered_by": target.discovered_by,
        "discovered_from": target.discovered_from,
        "scope_reason": target.scope_reason,
        "rejection_key": target.rejection_key,
        "created_at": target.created_at,
        "updated_at": target.updated_at,
        "metadata": dict(target.metadata),
    }


def serialize_scope_policy(policy: ScopePolicy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "project_id": policy.session_id,
        "allowed_hosts": list(policy.allowed_hosts),
        "allowed_domains": list(policy.allowed_domains),
        "allowed_cidrs": list(policy.allowed_cidrs),
        "allowed_ports": list(policy.allowed_ports),
        "allowed_protocols": list(policy.allowed_protocols),
        "denied_targets": list(policy.denied_targets),
        "allowed_tool_categories": list(policy.allowed_tool_categories),
        "max_concurrency": policy.max_concurrency,
        "rate_limit_per_minute": policy.rate_limit_per_minute,
        "confirmation_required_actions": list(policy.confirmation_required_actions),
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def serialize_dashboard(dashboard: SessionDashboard) -> dict[str, Any]:
    return {
        "project": serialize_project(dashboard.project),
        "session": serialize_target_session(dashboard.session),
        "active_targets": list(dashboard.active_targets),
        "pending_targets": list(dashboard.pending_targets),
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
            summary=request.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": serialize_target_session(session)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = TargetSessionService.from_settings().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"session": serialize_target_session(session)}


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, request: TargetSessionPatchRequest) -> dict[str, Any]:
    changes = request.model_dump(exclude_unset=True)
    try:
        session = TargetSessionService.from_settings().update_session(
            session_id,
            name=changes.get("name"),
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


@router.get("/projects/{project_id}/scope")
async def get_project_scope(project_id: str) -> dict[str, Any]:
    try:
        policy = TargetAdmissionService.from_settings().require_scope_policy(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"scope": serialize_scope_policy(policy)}


@router.patch("/projects/{project_id}/scope")
async def patch_project_scope(project_id: str, request: ScopePolicyPatchRequest) -> dict[str, Any]:
    service = TargetAdmissionService.from_settings()
    try:
        policy = service.require_scope_policy(project_id)
        changes = request.model_dump(exclude_unset=True)
        for field_name, value in changes.items():
            setattr(policy, field_name, list(value or []))
        saved = service.save_scope_policy(project_id, policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"scope": serialize_scope_policy(saved)}


@router.get("/projects/{project_id}/targets")
async def list_project_targets(project_id: str, status: TargetPoolStatus | None = None) -> dict[str, Any]:
    try:
        targets = TargetAdmissionService.from_settings().list_targets(
            project_identifier=project_id,
            status=status,
            limit=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"targets": [serialize_target(target) for target in targets]}


@router.post("/projects/{project_id}/targets/propose", status_code=201)
async def propose_project_target(project_id: str, request: TargetProposalRequest) -> dict[str, Any]:
    try:
        result = TargetAdmissionService.from_settings().propose_target(
            project_identifier=project_id,
            value=request.value,
            source=request.source,
            evidence_id=request.evidence_id,
            discovered_by=request.discovered_by,
            discovered_from=request.discovered_from,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"admission": {"status": result.status, "reason": result.reason, "target": serialize_target(result.target)}}


@router.post("/targets/{target_id}/approve")
async def approve_target(target_id: str) -> dict[str, Any]:
    try:
        result = TargetAdmissionService.from_settings().approve_target(target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"admission": {"status": result.status, "reason": result.reason, "target": serialize_target(result.target)}}


@router.post("/targets/{target_id}/reject")
async def reject_target(target_id: str) -> dict[str, Any]:
    try:
        result = TargetAdmissionService.from_settings().reject_target(target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"admission": {"status": result.status, "reason": result.reason, "target": serialize_target(result.target)}}
