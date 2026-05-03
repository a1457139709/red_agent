from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .contracts import ServerEventEnvelope

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def event_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    sequence = 0

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

    await send_event(
        "connection.connected",
        {"message": "connected", "channel": "events"},
    )

    try:
        while True:
            message = await websocket.receive_json()
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
