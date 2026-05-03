from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class ControlCenterService:
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None):
        return cls(settings or get_settings())
