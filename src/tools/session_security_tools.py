from __future__ import annotations

import json
from typing import Any

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import AdmissionOutcome, ScopeValidator
from tools.error_signals import RECOVERABLE_TOOL_ERROR_PREFIX
from tools.executor import SecurityToolExecutionError, SecurityToolExecutor
from utils.truncate import truncate_tool_output

from .registry import invokable
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


@invokable
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


@invokable
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


@invokable
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


@invokable
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


@invokable
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
