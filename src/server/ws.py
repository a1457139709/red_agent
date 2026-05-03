from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .contracts import ServerEventEnvelope

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def event_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    sequence = 1
    await websocket.send_json(
        ServerEventEnvelope.create(
            sequence=sequence,
            event_kind="connection.connected",
            payload={"message": "connected", "channel": "events"},
        ).to_dict()
    )

    try:
        while True:
            message = await websocket.receive_json()
            sequence += 1
            if message.get("event_kind") == "ping":
                await websocket.send_json(
                    ServerEventEnvelope.create(
                        sequence=sequence,
                        event_kind="connection.pong",
                        payload={"message": "pong"},
                    ).to_dict()
                )
    except WebSocketDisconnect:
        return
