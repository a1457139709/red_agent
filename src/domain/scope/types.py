from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    allowed: bool
    reason_code: str | None
    message: str

    @classmethod
    def allow(cls, message: str = "Allowed by scope policy") -> "ScopeDecision":
        return cls(True, None, message)

    @classmethod
    def deny(cls, reason_code: str, message: str) -> "ScopeDecision":
        return cls(False, reason_code, message)
