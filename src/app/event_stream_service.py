from __future__ import annotations

from agent.settings import Settings, get_settings
from models.control_center import Event
from storage.repositories.control_center import EventRepository
from storage.sqlite import SQLiteStorage
from server.contracts import ServerEventEnvelope

from .control_center_base import ControlCenterService


class EventStreamService(ControlCenterService):
    def __init__(self, settings: Settings) -> None:
        object.__setattr__(self, "settings", settings)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EventStreamService":
        return cls(settings or get_settings())

    def list_event_envelopes(
        self,
        *,
        session_id: str | None = None,
        project_id: str | None = None,
        since_sequence: int | None = None,
        limit: int | None = 50,
    ) -> list[ServerEventEnvelope]:
        storage = SQLiteStorage(self.settings.sqlite_path)
        events = EventRepository(storage).list(
            session_id=session_id,
            project_id=project_id,
            since_sequence=since_sequence,
            limit=limit,
            descending=False,
        )
        return [self.envelope_for_event(event) for event in events]

    def envelope_for_event(self, event: Event) -> ServerEventEnvelope:
        return ServerEventEnvelope.create(
            event_id=event.id,
            sequence=event.sequence,
            event_kind=event.event_kind,
            timestamp=event.created_at,
            payload=dict(event.payload),
            project_id=event.project_id,
            session_id=event.session_id,
            task_id=event.task_id,
        )
