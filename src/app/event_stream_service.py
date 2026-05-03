from __future__ import annotations

from agent.settings import Settings, get_settings
from models.control_center import Event
from server.contracts import ServerEventEnvelope

from .control_center_base import ControlCenterService


class EventStreamService(ControlCenterService):
    def __init__(self, settings: Settings) -> None:
        object.__setattr__(self, "settings", settings)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EventStreamService":
        return cls(settings or get_settings())

    def envelope_for_event(self, event: Event) -> ServerEventEnvelope:
        return ServerEventEnvelope.create(
            sequence=event.sequence,
            event_kind=event.event_kind,
            payload=dict(event.payload),
            project_id=event.project_id,
            session_id=event.session_id,
            task_id=event.task_id,
        )
