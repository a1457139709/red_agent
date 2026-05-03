from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.scanner_service import ScannerService, ScannerToolConfig
from scanners.contracts import ToolStatus

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolConfigPatch(BaseModel):
    tools: dict[str, dict[str, Any]]


def serialize_tool_status(status: ToolStatus) -> dict[str, Any]:
    return {
        "name": status.name,
        "available": status.available,
        "path": status.path,
        "version": status.version,
        "error": status.error,
    }


def serialize_tool_config(config: ScannerToolConfig) -> dict[str, Any]:
    return config.to_dict()


@router.get("/status")
async def get_tool_status() -> dict[str, Any]:
    statuses = ScannerService.from_settings().get_tool_status()
    return {"tools": [serialize_tool_status(status) for status in statuses]}


@router.get("/config")
async def get_tool_config() -> dict[str, Any]:
    return {"config": serialize_tool_config(ScannerService.from_settings().get_config())}


@router.patch("/config")
async def patch_tool_config(request: ToolConfigPatch) -> dict[str, Any]:
    try:
        config = ScannerService.from_settings().update_config(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"config": serialize_tool_config(config)}
