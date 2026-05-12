from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.attack_path_service import AttackPathNodeDetail, AttackPathService
from models.control_center import AttackPathNode, Evidence, Finding, Flag

router = APIRouter(prefix="/api", tags=["workspace"])


class AttackPathCreateRequest(BaseModel):
    stage: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(default="open", min_length=1)
    source_ref: str | None = None
    next_action: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class EvidenceCreateRequest(BaseModel):
    evidence_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str | None = None
    content_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    source_task_id: str | None = None
    attack_path_node_id: str | None = None


class FindingPatchRequest(BaseModel):
    severity: str | None = None
    status: str | None = None
    title: str | None = None
    description: str | None = None
    evidence_refs: list[str] | None = None


class FlagCreateRequest(BaseModel):
    flag_type: str = Field(min_length=1)
    value: str = Field(min_length=1)
    source_evidence_id: str | None = None


def serialize_evidence(evidence: Evidence) -> dict[str, Any]:
    return {
        "id": evidence.id,
        "public_id": evidence.public_id,
        "project_id": evidence.project_id,
        "session_id": evidence.session_id,
        "source_task_id": evidence.source_task_id,
        "evidence_type": evidence.evidence_type,
        "title": evidence.title,
        "summary": evidence.summary,
        "content_ref": evidence.content_ref,
        "payload": dict(evidence.payload),
        "created_at": evidence.created_at,
    }


def serialize_attack_path_node(node: AttackPathNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "public_id": node.public_id,
        "project_id": node.project_id,
        "session_id": node.session_id,
        "stage": node.stage,
        "title": node.title,
        "status": node.status,
        "source_ref": node.source_ref,
        "next_action": node.next_action,
        "created_at": node.created_at,
    }


def serialize_attack_path_detail(detail: AttackPathNodeDetail) -> dict[str, Any]:
    payload = serialize_attack_path_node(detail.node)
    payload["evidence"] = [serialize_evidence(item) for item in detail.evidence]
    return payload


def serialize_finding(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "public_id": finding.public_id,
        "project_id": finding.project_id,
        "session_id": finding.session_id,
        "severity": finding.severity,
        "status": finding.status,
        "title": finding.title,
        "description": finding.description,
        "evidence_refs": list(finding.evidence_refs),
        "created_at": finding.created_at,
        "updated_at": finding.updated_at,
    }


def serialize_flag(flag: Flag) -> dict[str, Any]:
    return {
        "id": flag.id,
        "public_id": flag.public_id,
        "project_id": flag.project_id,
        "session_id": flag.session_id,
        "flag_type": flag.flag_type,
        "value": flag.value,
        "source_evidence_id": flag.source_evidence_id,
        "created_at": flag.created_at,
    }


@router.get("/sessions/{session_id}/attack-path")
async def list_attack_path(session_id: str) -> dict[str, list[dict[str, Any]]]:
    try:
        nodes = AttackPathService.from_settings().list_attack_path(session_identifier=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"nodes": [serialize_attack_path_detail(node) for node in nodes]}


@router.post("/sessions/{session_id}/attack-path", status_code=201)
async def create_attack_path_node(session_id: str, request: AttackPathCreateRequest) -> dict[str, Any]:
    try:
        node = AttackPathService.from_settings().create_attack_path_node(
            session_identifier=session_id,
            stage=request.stage,
            title=request.title,
            status=request.status,
            source_ref=request.source_ref,
            next_action=request.next_action,
            evidence_ids=request.evidence_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"node": serialize_attack_path_detail(node)}


@router.get("/sessions/{session_id}/evidence")
async def list_evidence(session_id: str) -> dict[str, list[dict[str, Any]]]:
    try:
        evidence = AttackPathService.from_settings().list_evidence(session_identifier=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"evidence": [serialize_evidence(item) for item in evidence]}


@router.post("/sessions/{session_id}/evidence", status_code=201)
async def create_evidence(session_id: str, request: EvidenceCreateRequest) -> dict[str, Any]:
    try:
        evidence, node = AttackPathService.from_settings().create_evidence(
            session_identifier=session_id,
            evidence_type=request.evidence_type,
            title=request.title,
            summary=request.summary,
            content_ref=request.content_ref,
            payload=request.payload,
            source_task_id=request.source_task_id,
            attack_path_node_id=request.attack_path_node_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"evidence": serialize_evidence(evidence), "node": serialize_attack_path_detail(node)}


@router.get("/sessions/{session_id}/findings")
async def list_findings(session_id: str) -> dict[str, list[dict[str, Any]]]:
    try:
        findings = AttackPathService.from_settings().list_findings(session_identifier=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"findings": [serialize_finding(item) for item in findings]}


@router.patch("/findings/{finding_id}")
async def patch_finding(finding_id: str, request: FindingPatchRequest) -> dict[str, Any]:
    try:
        finding = AttackPathService.from_settings().update_finding(
            finding_identifier=finding_id,
            severity=request.severity,
            status=request.status,
            title=request.title,
            description=request.description,
            evidence_refs=request.evidence_refs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"finding": serialize_finding(finding)}


@router.get("/sessions/{session_id}/flags")
async def list_flags(session_id: str) -> dict[str, list[dict[str, Any]]]:
    try:
        flags = AttackPathService.from_settings().list_flags(session_identifier=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"flags": [serialize_flag(item) for item in flags]}


@router.post("/sessions/{session_id}/flags", status_code=201)
async def create_flag(session_id: str, request: FlagCreateRequest) -> dict[str, Any]:
    try:
        flag, node = AttackPathService.from_settings().create_flag(
            session_identifier=session_id,
            flag_type=request.flag_type,
            value=request.value,
            source_evidence_id=request.source_evidence_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"flag": serialize_flag(flag), "node": serialize_attack_path_detail(node)}
