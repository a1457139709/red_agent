from __future__ import annotations

from dataclasses import dataclass, field
from re import Match
import re

from models.session import SessionTarget, SessionTargetKind

from .contracts import ControllerIntent


URL_PATTERN = re.compile(r"https?://[^\s/$.?#].[^\s]*", re.IGNORECASE)
CIDR_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b")
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_PATTERN = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b", re.IGNORECASE)
HOST_PATTERN = re.compile(r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9-]{1,63})+\b", re.IGNORECASE)
SESSION_ID_PATTERN = re.compile(r"\bS\d{4}\b", re.IGNORECASE)

RECORD_LOOKUP_KEYWORDS = (
    "what did you already do",
    "what have you done",
    "show me what you already did",
    "show session",
    "show the session",
    "show status",
    "show the status",
    "show me the status",
    "what happened",
    "what's the status",
    "whats the status",
)
@dataclass(slots=True)
class IntentClassification:
    intent: ControllerIntent
    extracted_targets: list[SessionTarget] = field(default_factory=list)
    explicit_record_scope: str | None = None
    unsupported_reason: str | None = None


def classify_input(raw_input: str) -> IntentClassification:
    text = raw_input.strip()
    lowered = text.lower()

    if not text:
        return IntentClassification(
            intent=ControllerIntent.UNSUPPORTED_REQUEST,
            unsupported_reason="Please enter a request.",
        )

    if text.startswith("/"):
        return IntentClassification(intent=ControllerIntent.ADVANCED_COMMAND_REQUEST)

    if not any(character.isalnum() for character in text):
        return IntentClassification(
            intent=ControllerIntent.UNSUPPORTED_REQUEST,
            unsupported_reason="I need a plain-language request or an advanced slash command.",
        )

    extracted_targets = extract_targets(text)
    explicit_record_scope = extract_record_scope(text)

    if any(keyword in lowered for keyword in RECORD_LOOKUP_KEYWORDS):
        return IntentClassification(
            intent=ControllerIntent.RECORD_LOOKUP_REQUEST,
            explicit_record_scope=explicit_record_scope,
        )

    return IntentClassification(
        intent=ControllerIntent.NORMAL_REQUEST,
        extracted_targets=extracted_targets,
    )


def extract_targets(text: str) -> list[SessionTarget]:
    targets: list[SessionTarget] = []
    seen: set[tuple[SessionTargetKind, str]] = set()
    occupied_spans: list[tuple[int, int]] = []

    def add_target(kind: SessionTargetKind, value: str) -> None:
        normalized = value.strip().rstrip(".,;:")
        key = (kind, normalized.lower())
        if not normalized or key in seen:
            return
        seen.add(key)
        targets.append(SessionTarget(kind=kind, value=normalized))

    def overlaps_existing_span(start: int, end: int) -> bool:
        return any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied_spans)

    def occupy_span(start: int, end: int) -> None:
        occupied_spans.append((start, end))

    for match in URL_PATTERN.finditer(text):
        add_target(SessionTargetKind.URL, match.group(0))
        occupy_span(*match.span())
    for match in CIDR_PATTERN.finditer(text):
        if overlaps_existing_span(*match.span()):
            continue
        add_target(SessionTargetKind.CIDR, match.group(0))
        occupy_span(*match.span())
    for match in IP_PATTERN.finditer(text):
        if overlaps_existing_span(*match.span()):
            continue
        _add_ip_target(match, add_target)
        occupy_span(*match.span())
    for match in DOMAIN_PATTERN.finditer(text):
        if overlaps_existing_span(*match.span()):
            continue
        add_target(SessionTargetKind.DOMAIN, match.group(0))
        occupy_span(*match.span())
    for match in HOST_PATTERN.finditer(text):
        if overlaps_existing_span(*match.span()):
            continue
        candidate = match.group(0)
        if candidate.lower().startswith("http"):
            continue
        if DOMAIN_PATTERN.fullmatch(candidate):
            continue
        add_target(SessionTargetKind.HOST, candidate)
        occupy_span(*match.span())

    return targets


def extract_record_scope(text: str) -> str | None:
    lowered = text.lower()
    match = SESSION_ID_PATTERN.search(text)
    if match is not None:
        return match.group(0).upper()
    if "latest" in lowered or "last" in lowered:
        return "latest"
    if "current" in lowered:
        return "current"
    return None

def _add_ip_target(
    match: Match[str],
    add_target,
) -> None:
    candidate = match.group(0)
    octets = candidate.split(".")
    if any(int(octet) > 255 for octet in octets):
        return
    add_target(SessionTargetKind.IP, candidate)
