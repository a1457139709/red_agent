from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FindingCandidate:
    finding_type: str
    title: str
    target_ref: str
    severity: str
    confidence: float
    summary: str
    impact: str | None = None
    reproduction_notes: str | None = None
    next_action: str | None = None
    dedupe_key: str | None = None
