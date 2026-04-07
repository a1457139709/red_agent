from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import socket

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import TargetDescriptor
from tools.contracts import (
    EvidenceCandidate,
    FindingCandidate,
    SecurityToolInvocation,
    SecurityToolResult,
    normalize_port,
    normalize_timeout,
)

from ._common import build_socket_target, decode_payload, normalize_positive_int, parse_network_target

DEFAULT_BANNER_READ_BYTES = 512
MAX_BANNER_READ_BYTES = 4096
DEFAULT_BANNER_PROBE = "none"
ALLOWED_BANNER_PROBES = {"none", "http", "redis"}


def _normalize_probe(value: object | None) -> str:
    if value in (None, ""):
        return DEFAULT_BANNER_PROBE
    probe = str(value).strip().lower()
    if probe not in ALLOWED_BANNER_PROBES:
        raise ValueError(f"probe must be one of: {', '.join(sorted(ALLOWED_BANNER_PROBES))}.")
    return probe


def _probe_payload(probe: str, host: str) -> bytes:
    if probe == "http":
        return f"HEAD / HTTP/1.0\r\nHost: {host}\r\n\r\n".encode("ascii")
    if probe == "redis":
        return b"PING\r\n"
    return b""


def _finding_candidates_for_banner(*, host: str, port: int, banner: str) -> list[FindingCandidate]:
    normalized_banner = banner.lower()
    indicators: list[tuple[str, str]] = []
    if port == 23 or "telnet" in normalized_banner:
        indicators.append(("cleartext_telnet", "Cleartext Telnet service exposed"))
    if port == 21 or "ftp" in normalized_banner:
        indicators.append(("cleartext_ftp", "Cleartext FTP service exposed"))
    if port == 6379 or "redis" in normalized_banner:
        indicators.append(("redis_banner", "Redis service exposed without TLS evidence"))

    findings: list[FindingCandidate] = []
    for finding_type, title in indicators:
        findings.append(
            FindingCandidate(
                finding_type=finding_type,
                title=title,
                target_ref=build_socket_target(host, port),
                severity="medium",
                confidence="medium",
                summary=f"Banner grab identified '{banner[:120]}' on {host}:{port}.",
                impact="Cleartext administrative or database services increase the exposed attack surface.",
                reproduction_notes=f"Connect to {host}:{port} and read the initial banner or service response.",
                next_action="Confirm intended exposure and add protocol-specific verification.",
            )
        )
    return findings


class BannerGrabSecurityTool:
    name = "banner_grab"
    category = "recon"

    def validate_invocation(
        self,
        *,
        target: str,
        arguments: Mapping[str, Any],
        policy: ScopePolicy,
    ) -> SecurityToolInvocation:
        del policy
        requested_port = normalize_port(arguments.get("port"))
        host, target_port, _scheme = parse_network_target(target, default_port=requested_port)
        port = target_port or requested_port
        if port is None:
            raise ValueError("banner_grab requires a target port.")
        timeout_seconds = normalize_timeout(arguments.get("timeout_seconds"))
        max_read_bytes = normalize_positive_int(
            arguments.get("max_read_bytes"),
            field_name="max_read_bytes",
            default=DEFAULT_BANNER_READ_BYTES,
            maximum=MAX_BANNER_READ_BYTES,
        )
        probe = _normalize_probe(arguments.get("probe"))
        return SecurityToolInvocation(
            target=build_socket_target(host, port),
            timeout_seconds=timeout_seconds,
            protocol="tcp",
            port=port,
            metadata={"probe": probe},
            execution_args={
                "host": host,
                "port": port,
                "probe": probe,
                "max_read_bytes": max_read_bytes,
            },
        )

    def execute(
        self,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult:
        host = str(invocation.execution_args["host"])
        port = int(invocation.execution_args["port"])
        probe = str(invocation.execution_args["probe"])
        max_read_bytes = int(invocation.execution_args["max_read_bytes"])

        try:
            with socket.create_connection((host, port), timeout=invocation.timeout_seconds) as connection:
                connection.settimeout(invocation.timeout_seconds)
                payload = _probe_payload(probe, host)
                if payload:
                    connection.sendall(payload)
                banner_bytes = connection.recv(max_read_bytes)
        except Exception as exc:
            raise ValueError(f"banner_grab failed: {exc}.") from exc

        banner_text = decode_payload(banner_bytes).strip()
        summary = f"Banner grab on {target.normalized_target} captured {len(banner_bytes)} bytes."
        payload = {
            "host": host,
            "port": port,
            "probe": probe,
            "banner": banner_text,
            "banner_bytes": len(banner_bytes),
        }
        evidence = EvidenceCandidate(
            evidence_type="banner",
            target_ref=target.normalized_target,
            title=f"Banner grab for {target.normalized_target}",
            summary=summary,
            content_type="text/plain",
            payload=payload,
        )
        findings = _finding_candidates_for_banner(host=host, port=port, banner=banner_text)
        return SecurityToolResult(
            tool_name=self.name,
            target=target.normalized_target,
            summary=summary,
            payload=payload,
            evidence_candidates=[evidence],
            finding_candidates=findings,
        )
