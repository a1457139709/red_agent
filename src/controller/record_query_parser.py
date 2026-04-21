from __future__ import annotations

import re

from .contracts import RecordLookupKind, RecordQueryRequest, ReportType


SESSION_PUBLIC_ID_PATTERN = re.compile(r"^S\d{4}$", re.IGNORECASE)
ARTIFACT_PUBLIC_ID_PATTERN = re.compile(r"^A\d{4}$", re.IGNORECASE)
FINDING_PUBLIC_ID_PATTERN = re.compile(r"^F\d{4}$", re.IGNORECASE)
REPORT_PUBLIC_ID_PATTERN = re.compile(r"^RP\d{4}$", re.IGNORECASE)
SCOPE_TOKENS = {"current", "latest"}
REPORT_TYPES = {
    ReportType.SESSION_SUMMARY.value: ReportType.SESSION_SUMMARY,
    ReportType.FINDINGS_SUMMARY.value: ReportType.FINDINGS_SUMMARY,
    ReportType.OPERATOR_REPORT.value: ReportType.OPERATOR_REPORT,
}
LOOKUP_COMMANDS = {
    "/status": RecordLookupKind.SESSION_HISTORY,
    "/s": RecordLookupKind.SESSION_HISTORY,
    "/history": RecordLookupKind.SESSION_HISTORY,
    "/h": RecordLookupKind.SESSION_HISTORY,
    "/steps": RecordLookupKind.EXECUTION_STEPS,
    "/artifacts": RecordLookupKind.ARTIFACTS,
    "/a": RecordLookupKind.ARTIFACTS,
    "/findings": RecordLookupKind.FINDINGS,
    "/f": RecordLookupKind.FINDINGS,
    "/reports": RecordLookupKind.REPORTS,
    "/r": RecordLookupKind.REPORTS,
}


def parse_record_query_command(command: str) -> RecordQueryRequest | None:
    stripped = command.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split()
    if not parts:
        return None

    command_name = parts[0].lower()
    args = parts[1:]

    if command_name in LOOKUP_COMMANDS:
        scope_hint = _parse_optional_scope_hint(
            args,
            usage=f"Usage: {parts[0]} [current|latest|S0001]",
        )
        return RecordQueryRequest(
            kind=LOOKUP_COMMANDS[command_name],
            explicit_scope=scope_hint,
            source_command=command_name,
        )

    if command_name == "/show":
        if not args or len(args) > 2:
            raise ValueError("Usage: /show <public_id> [current|latest|S0001]")
        lookup_identifier = args[0].upper()
        kind = _kind_from_lookup_identifier(lookup_identifier)
        scope_hint = _parse_optional_scope_hint(
            args[1:],
            usage="Usage: /show <public_id> [current|latest|S0001]",
        )
        explicit_scope = lookup_identifier if kind == RecordLookupKind.SESSION_HISTORY else scope_hint
        return RecordQueryRequest(
            kind=kind,
            explicit_scope=explicit_scope,
            lookup_identifier=lookup_identifier,
            source_command=command_name,
        )

    if command_name == "/why":
        if not args or len(args) > 2:
            raise ValueError("Usage: /why <finding_public_id> [current|latest|S0001]")
        lookup_identifier = args[0].upper()
        if not FINDING_PUBLIC_ID_PATTERN.fullmatch(lookup_identifier):
            raise ValueError("Usage: /why <finding_public_id> [current|latest|S0001]")
        scope_hint = _parse_optional_scope_hint(
            args[1:],
            usage="Usage: /why <finding_public_id> [current|latest|S0001]",
        )
        return RecordQueryRequest(
            kind=RecordLookupKind.FINDING_EXPLANATION,
            explicit_scope=scope_hint,
            lookup_identifier=lookup_identifier,
            source_command=command_name,
        )

    if command_name == "/report":
        if not args or len(args) > 2:
            raise ValueError(
                "Usage: /report <session_summary|findings_summary|operator_report> [current|latest|S0001]"
            )
        report_type = REPORT_TYPES.get(args[0].lower())
        if report_type is None:
            return None
        scope_hint = _parse_optional_scope_hint(
            args[1:],
            usage="Usage: /report <session_summary|findings_summary|operator_report> [current|latest|S0001]",
        )
        return RecordQueryRequest(
            kind=RecordLookupKind.REPORTS,
            explicit_scope=scope_hint,
            report_type=report_type,
            source_command=command_name,
        )

    return None


def _parse_optional_scope_hint(args: list[str], *, usage: str) -> str | None:
    if not args:
        return None
    if len(args) != 1:
        raise ValueError(usage)
    token = args[0].strip()
    if not token:
        raise ValueError(usage)
    normalized = token.lower()
    if normalized in SCOPE_TOKENS:
        return normalized
    upper_token = token.upper()
    if SESSION_PUBLIC_ID_PATTERN.fullmatch(upper_token):
        return upper_token
    raise ValueError(usage)


def _kind_from_lookup_identifier(identifier: str) -> RecordLookupKind:
    if SESSION_PUBLIC_ID_PATTERN.fullmatch(identifier):
        return RecordLookupKind.SESSION_HISTORY
    if ARTIFACT_PUBLIC_ID_PATTERN.fullmatch(identifier):
        return RecordLookupKind.ARTIFACTS
    if FINDING_PUBLIC_ID_PATTERN.fullmatch(identifier):
        return RecordLookupKind.FINDINGS
    if REPORT_PUBLIC_ID_PATTERN.fullmatch(identifier):
        return RecordLookupKind.REPORTS
    raise ValueError("Usage: /show <public_id> [current|latest|S0001]")
