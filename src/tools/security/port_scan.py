from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import socket

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import TargetDescriptor
from tools.contracts import (
    EvidenceCandidate,
    SecurityToolInvocation,
    SecurityToolResult,
    normalize_port_list,
    normalize_timeout,
)

from ._common import build_socket_target, parse_network_target


def _resolve_scan_ports(
    *,
    target_port: int | None,
    arguments: Mapping[str, Any],
    policy: ScopePolicy,
) -> list[int]:
    explicit_ports = normalize_port_list(arguments.get("ports"))
    if explicit_ports:
        return explicit_ports
    if target_port is not None:
        return [target_port]
    if policy.allowed_ports:
        return list(policy.allowed_ports)
    raise ValueError("port_scan requires explicit ports or a scope policy with allowed_ports.")


class PortScanSecurityTool:
    name = "port_scan"
    category = "recon"

    def validate_invocation(
        self,
        *,
        target: str,
        arguments: Mapping[str, Any],
        policy: ScopePolicy,
    ) -> SecurityToolInvocation:
        host, target_port, _scheme = parse_network_target(target)
        ports = _resolve_scan_ports(target_port=target_port, arguments=arguments, policy=policy)
        if policy.allowed_ports:
            denied_ports = [port for port in ports if port not in policy.allowed_ports]
            if denied_ports:
                denied_text = ", ".join(str(port) for port in denied_ports)
                raise ValueError(f"Requested ports are outside the scope policy: {denied_text}.")
        timeout_seconds = normalize_timeout(arguments.get("timeout_seconds"))
        return SecurityToolInvocation(
            target=host,
            timeout_seconds=timeout_seconds,
            protocol="tcp",
            metadata={"ports": ports},
            execution_args={"host": host, "ports": ports},
        )

    def execute(
        self,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult:
        host = str(invocation.execution_args["host"])
        ports = list(invocation.execution_args["ports"])
        results: list[dict[str, Any]] = []

        for port in ports:
            status = "closed"
            error: str | None = None
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                    client.settimeout(invocation.timeout_seconds)
                    code = client.connect_ex((host, int(port)))
                    if code == 0:
                        status = "open"
                    else:
                        error = str(code)
            except socket.timeout:
                status = "timed_out"
            except Exception as exc:
                status = "error"
                error = str(exc)
            results.append({"port": int(port), "status": status, "error": error})

        open_ports = [entry["port"] for entry in results if entry["status"] == "open"]
        summary = (
            f"TCP port scan for {target.normalized_target} checked {len(results)} port(s) "
            f"and found {len(open_ports)} open."
        )
        payload = {"host": host, "ports": results, "open_ports": open_ports}
        evidence = EvidenceCandidate(
            evidence_type="port_scan",
            target_ref=target.normalized_target,
            title=f"TCP port scan for {target.normalized_target}",
            summary=summary,
            content_type="application/json",
            payload=payload,
        )
        return SecurityToolResult(
            tool_name=self.name,
            target=target.normalized_target,
            summary=summary,
            payload=payload,
            evidence_candidates=[evidence],
        )
