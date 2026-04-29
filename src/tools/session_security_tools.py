from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import AdmissionOutcome, ScopeValidator
from tools.error_signals import RECOVERABLE_TOOL_ERROR_PREFIX
from tools.executor import SecurityToolExecutionError, SecurityToolExecutor
from utils.truncate import truncate_tool_output

from .registry import register_tool
from .security import AVAILABLE_SECURITY_TOOLS


_SECURITY_TOOL_EXECUTOR = SecurityToolExecutor(
    {tool.name: tool for tool in AVAILABLE_SECURITY_TOOLS}
)
_SCOPE_VALIDATOR = ScopeValidator()


def _build_inline_session_policy(*, session_id: str, tool_category: str) -> ScopePolicy:
    return ScopePolicy.create(
        session_id=session_id,
        allowed_tool_categories=[tool_category],
    )


def _compact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in arguments.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        compact[key] = value
    return compact


def _format_result(tool_name: str, summary: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return truncate_tool_output(tool_name, f"{summary}\n{body}")


def _recoverable_error(message: str) -> str:
    return f"{RECOVERABLE_TOOL_ERROR_PREFIX}{message}"


def _run_security_tool(
    *,
    tool_name: str,
    target: str,
    arguments: dict[str, Any],
) -> str:
    normalized_target = target.strip()
    if not normalized_target:
        return _recoverable_error("Error: target must not be empty.")

    try:
        tool = _SECURITY_TOOL_EXECUTOR.get_tool(tool_name)
        policy = _build_inline_session_policy(
            session_id=f"session-inline:{tool_name}",
            tool_category=tool.category,
        )
        invocation = _SECURITY_TOOL_EXECUTOR.validate(
            tool_name,
            target=normalized_target,
            arguments=_compact_arguments(arguments),
            policy=policy,
        )
        admission_request = invocation.to_admission_request(
            session_id=policy.session_id,
            job_id=None,
            tool_name=tool.name,
            tool_category=tool.category,
        )
        admission_decision = _SCOPE_VALIDATOR.evaluate(policy, admission_request)
        if admission_decision.outcome != AdmissionOutcome.ALLOWED:
            return _recoverable_error(f"Error: {admission_decision.message}")
        result = _SECURITY_TOOL_EXECUTOR.execute(
            tool_name,
            invocation=invocation,
            target=admission_decision.target,
        )
    except SecurityToolExecutionError as exc:
        return _recoverable_error(f"Error: {exc.error}")
    except Exception as exc:
        return _recoverable_error(f"Error: {exc}")

    payload = {
        "tool_name": result.tool_name,
        "target": result.target,
        "summary": result.summary,
        "payload": result.payload,
        "artifact_count": len(result.evidence_candidates),
        "finding_count": len(result.finding_candidates),
    }
    return _format_result(tool_name, result.summary, payload)


@register_tool
@tool(
    "dns_lookup",
    description=(
        "Run a DNS lookup using the typed security runtime and return a structured summary."
    ),
    args_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Domain or hostname to query.",
            },
            "record_type": {
                "type": "string",
                "description": "DNS record type such as A, AAAA, CNAME, TXT, MX.",
            },
            "nameserver": {
                "type": "string",
                "description": "Resolver IP address.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Request timeout in seconds.",
            },
        },
        "required": ["target"],
    },
)
def dns_lookup(
    target: str,
    record_type: str = "A",
    nameserver: str = "8.8.8.8",
    timeout_seconds: int | None = None,
) -> str:
    return _run_security_tool(
        tool_name="dns_lookup",
        target=target,
        arguments={
            "record_type": record_type,
            "nameserver": nameserver,
            "timeout_seconds": timeout_seconds,
        },
    )


@register_tool
@tool(
    "http_probe",
    description=(
        "Probe an HTTP(S) target with the typed security runtime and return structured metadata."
    ),
    args_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Absolute URL target.",
            },
            "method": {
                "type": "string",
                "description": "HTTP method (GET or HEAD).",
            },
            "max_body_chars": {
                "type": "integer",
                "description": "Maximum response body characters to include.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Request timeout in seconds.",
            },
            "headers": {
                "type": "object",
                "description": "Optional request headers.",
            },
        },
        "required": ["target"],
    },
)
def http_probe(
    target: str,
    method: str = "GET",
    max_body_chars: int | None = None,
    timeout_seconds: int | None = None,
    headers: dict[str, Any] | None = None,
) -> str:
    return _run_security_tool(
        tool_name="http_probe",
        target=target,
        arguments={
            "method": method,
            "max_body_chars": max_body_chars,
            "timeout_seconds": timeout_seconds,
            "headers": headers,
        },
    )


@register_tool
@tool(
    "tls_inspect",
    description=(
        "Inspect TLS certificate and negotiated ciphers for a host or host:port target."
    ),
    args_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Host, host:port, or URL target.",
            },
            "port": {
                "type": "integer",
                "description": "Optional TLS port override.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Connection timeout in seconds.",
            },
        },
        "required": ["target"],
    },
)
def tls_inspect(
    target: str,
    port: int | None = None,
    timeout_seconds: int | None = None,
) -> str:
    return _run_security_tool(
        tool_name="tls_inspect",
        target=target,
        arguments={
            "port": port,
            "timeout_seconds": timeout_seconds,
        },
    )


@register_tool
@tool(
    "banner_grab",
    description=(
        "Grab a service banner from a host:port target using the typed security runtime."
    ),
    args_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Host or host:port target.",
            },
            "port": {
                "type": "integer",
                "description": "Optional port override when target omits port.",
            },
            "probe": {
                "type": "string",
                "description": "Probe mode (none/http/redis).",
            },
            "max_read_bytes": {
                "type": "integer",
                "description": "Maximum bytes to read from the service banner.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Connection timeout in seconds.",
            },
        },
        "required": ["target"],
    },
)
def banner_grab(
    target: str,
    port: int | None = None,
    probe: str = "none",
    max_read_bytes: int | None = None,
    timeout_seconds: int | None = None,
) -> str:
    return _run_security_tool(
        tool_name="banner_grab",
        target=target,
        arguments={
            "port": port,
            "probe": probe,
            "max_read_bytes": max_read_bytes,
            "timeout_seconds": timeout_seconds,
        },
    )


@register_tool
@tool(
    "port_scan",
    description=(
        "Run a typed TCP port scan and return open/closed status for requested ports."
    ),
    args_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Host, host:port, or URL target.",
            },
            "ports": {
                "type": ["array", "string"],
                "description": "Port list, e.g. [80,443] or '80,443'.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Connection timeout in seconds.",
            },
        },
        "required": ["target"],
    },
)
def port_scan(
    target: str,
    ports: list[int] | str | None = None,
    timeout_seconds: int | None = None,
) -> str:
    return _run_security_tool(
        tool_name="port_scan",
        target=target,
        arguments={
            "ports": ports,
            "timeout_seconds": timeout_seconds,
        },
    )


AVAILABLE_SESSION_SECURITY_TOOLS = [
    dns_lookup,
    http_probe,
    tls_inspect,
    banner_grab,
    port_scan,
]
