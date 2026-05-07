from __future__ import annotations

import asyncio

from agent.settings import get_settings
from app.event_stream_service import EventStreamService
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from storage.repositories.control_center import ProjectRepository, TargetSessionRepository
from storage.sqlite import SQLiteStorage

from .contracts import ServerEventEnvelope

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def event_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        project_id, session_id = _resolve_scope_ids(
            project_identifier=_optional_query_value(websocket.query_params.get("project_id")),
            session_identifier=_optional_query_value(websocket.query_params.get("session_id")),
        )
        since_sequence = _parse_int_query(websocket.query_params.get("since_sequence"), field_name="since_sequence")
        limit = _parse_int_query(websocket.query_params.get("limit"), field_name="limit")
        if limit is None:
            limit = 50
        replay = _parse_bool_query(websocket.query_params.get("replay"), default=True)
    except ValueError as exc:
        await websocket.send_json(
            ServerEventEnvelope.create(
                sequence=1,
                event_kind="error",
                payload={"code": "invalid_query", "message": str(exc)},
            ).to_dict()
        )
        await websocket.close()
        return

    stream_service = EventStreamService.from_settings(get_settings())
    last_persisted_sequence = since_sequence or 0
    sequence = last_persisted_sequence

    async def send_event(event_kind: str, payload: dict[str, object]) -> None:
        nonlocal sequence
        sequence += 1
        await websocket.send_json(
            ServerEventEnvelope.create(
                sequence=sequence,
                event_kind=event_kind,
                payload=payload,
            ).to_dict()
        )

    try:
        await websocket.send_json(
            ServerEventEnvelope.create(
                sequence=last_persisted_sequence,
                event_kind="connection.connected",
                payload={"message": "connected", "channel": "events"},
            ).to_dict()
        )

        replayed = (
            stream_service.list_event_envelopes(
                project_id=project_id,
                session_id=session_id,
                since_sequence=since_sequence,
                limit=limit,
            )
            if replay and (project_id is not None or session_id is not None)
            else []
        )
        for envelope in replayed:
            sequence = max(sequence, envelope.sequence)
            last_persisted_sequence = max(last_persisted_sequence, envelope.sequence)
            await websocket.send_json(envelope.to_dict())
    except WebSocketDisconnect:
        return

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.25)
            except TimeoutError:
                pending = stream_service.list_event_envelopes(
                    project_id=project_id,
                    session_id=session_id,
                    since_sequence=last_persisted_sequence,
                    limit=50,
                )
                for envelope in pending:
                    last_persisted_sequence = max(last_persisted_sequence, envelope.sequence)
                    await websocket.send_json(envelope.to_dict())
                continue
            if not isinstance(message, dict):
                await send_event(
                    "error",
                    {
                        "code": "invalid_message",
                        "message": "WebSocket messages must be JSON objects.",
                    },
                )
                continue
            if message.get("event_kind") == "ping":
                await send_event("connection.pong", {"message": "pong"})
                continue
            await send_event(
                "error",
                {
                    "code": "unknown_event_kind",
                    "message": "Unsupported WebSocket event kind.",
                    "event_kind": str(message.get("event_kind")),
                },
            )
    except ValueError:
        await send_event(
            "error",
            {
                "code": "invalid_json",
                "message": "WebSocket messages must be valid JSON.",
            },
        )
    except WebSocketDisconnect:
        return


def _optional_query_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _parse_int_query(value: str | None, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{field_name} must be zero or greater.")
    return parsed


def _parse_bool_query(value: str | None, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("replay must be a boolean value.")


def _resolve_scope_ids(
    *,
    project_identifier: str | None,
    session_identifier: str | None,
) -> tuple[str | None, str | None]:
    if project_identifier is None and session_identifier is None:
        return None, None
    settings = get_settings()
    storage = SQLiteStorage(settings.sqlite_path)
    project_id: str | None = None
    session_id: str | None = None
    if project_identifier is not None:
        project_id = ProjectRepository(storage).require(project_identifier).id
    if session_identifier is not None:
        session = TargetSessionRepository(storage).require(session_identifier)
        session_id = session.id
        if project_id is not None and session.project_id != project_id:
            raise ValueError("session_id does not belong to project_id.")
        project_id = project_id or session.project_id
    return project_id, session_id
