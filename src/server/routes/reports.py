from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.writeup_service import WriteupService
from models.control_center import CTFReport
from server.dependencies import AppRuntimeState, get_runtime_state

router = APIRouter(prefix="/api", tags=["reports"])


def serialize_report(report: CTFReport, *, content: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": report.id,
        "public_id": report.public_id,
        "project_id": report.project_id,
        "session_id": report.session_id,
        "report_type": report.report_type.value,
        "title": report.title,
        "summary": report.summary,
        "material_path": report.material_path,
        "artifact_path": report.artifact_path,
        "created_at": report.created_at,
        "metadata": dict(report.metadata),
    }
    if content is not None:
        payload["content"] = content
    return payload


@router.get("/sessions/{session_id}/reports")
async def list_session_reports(
    session_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, list[dict[str, Any]]]:
    try:
        reports = WriteupService.from_settings(runtime_state.settings).list_reports(session_identifier=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"reports": [serialize_report(report, content=_read_optional(report.artifact_path)) for report in reports]}


@router.post("/sessions/{session_id}/reports", status_code=201)
async def create_session_report(
    session_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> dict[str, Any]:
    try:
        result = WriteupService.from_settings(runtime_state.settings).generate_session_writeup(session_identifier=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"report": serialize_report(result.report, content=result.writeup_markdown)}


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    runtime_state: AppRuntimeState = Depends(get_runtime_state),
) -> FileResponse:
    try:
        report = WriteupService.from_settings(runtime_state.settings).require_report(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = Path(report.artifact_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=f"{report.public_id}.md")


def _read_optional(path: str) -> str | None:
    report_path = Path(path)
    if not report_path.is_file():
        return None
    return report_path.read_text(encoding="utf-8")
