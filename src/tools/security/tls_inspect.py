from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
import socket
import ssl

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

from ._common import build_socket_target, parse_network_target

DEFAULT_TLS_PORT = 443
TLS_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


def _normalize_name(entries: tuple[tuple[tuple[str, str], ...], ...] | tuple) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for part in entries or ():
        for key, value in part:
            normalized[str(key)] = str(value)
    return normalized


def _parse_cert_time(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        parsed = datetime.strptime(raw_value, TLS_DATE_FORMAT)
    except ValueError:
        return raw_value
    return parsed.replace(tzinfo=UTC).isoformat()


def _collect_findings(
    *,
    target_ref: str,
    cert: dict[str, Any],
    verification_error: str | None,
) -> list[FindingCandidate]:
    findings: list[FindingCandidate] = []
    subject = _normalize_name(cert.get("subject", ()))
    issuer = _normalize_name(cert.get("issuer", ()))
    subject_ref = subject.get("commonName") or target_ref
    not_before_raw = cert.get("notBefore")
    not_after_raw = cert.get("notAfter")
    now = datetime.now(UTC)

    if verification_error and "hostname" in verification_error.lower():
        findings.append(
            FindingCandidate(
                finding_type="tls_hostname_mismatch",
                title="TLS certificate hostname mismatch",
                target_ref=target_ref,
                severity="medium",
                confidence="high",
                summary=verification_error,
                impact="Clients may reject the service certificate because it does not match the requested host.",
                reproduction_notes=f"Attempt a verified TLS handshake against {target_ref}.",
                next_action="Confirm the intended certificate SANs and deployment configuration.",
            )
        )
    if subject and issuer and subject == issuer:
        findings.append(
            FindingCandidate(
                finding_type="tls_self_signed_certificate",
                title="Self-signed TLS certificate observed",
                target_ref=target_ref,
                severity="medium",
                confidence="medium",
                summary=f"The certificate for {subject_ref} appears to be self-signed.",
                impact="Self-signed certificates can break client trust and mask misconfiguration.",
                reproduction_notes=f"Inspect the certificate chain returned by {target_ref}.",
                next_action="Validate whether this endpoint should use an internal CA or a public certificate.",
            )
        )

    for raw_value, finding_type, title in (
        (not_after_raw, "tls_expired_certificate", "Expired TLS certificate observed"),
        (not_before_raw, "tls_not_yet_valid_certificate", "Not-yet-valid TLS certificate observed"),
    ):
        if not raw_value:
            continue
        try:
            parsed = datetime.strptime(raw_value, TLS_DATE_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            continue
        if finding_type == "tls_expired_certificate" and parsed < now:
            findings.append(
                FindingCandidate(
                    finding_type=finding_type,
                    title=title,
                    target_ref=target_ref,
                    severity="high",
                    confidence="high",
                    summary=f"The certificate for {subject_ref} expired at {parsed.isoformat()}.",
                    impact="Expired certificates break trust and may interrupt secure connectivity.",
                    reproduction_notes=f"Inspect the peer certificate returned by {target_ref}.",
                    next_action="Replace or renew the expired certificate.",
                )
            )
        if finding_type == "tls_not_yet_valid_certificate" and parsed > now:
            findings.append(
                FindingCandidate(
                    finding_type=finding_type,
                    title=title,
                    target_ref=target_ref,
                    severity="medium",
                    confidence="high",
                    summary=f"The certificate for {subject_ref} is not valid until {parsed.isoformat()}.",
                    impact="Clients may reject the endpoint until the certificate enters its validity period.",
                    reproduction_notes=f"Inspect the peer certificate returned by {target_ref}.",
                    next_action="Confirm certificate issuance dates and system time configuration.",
                )
            )
    return findings


def _handshake(
    *,
    host: str,
    port: int,
    timeout_seconds: int,
    verified: bool,
) -> tuple[dict[str, Any], str, tuple[str, str, int], str | None]:
    context = ssl.create_default_context()
    if not verified:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        with context.wrap_socket(connection, server_hostname=host) as tls_socket:
            cert = tls_socket.getpeercert()
            cipher = tls_socket.cipher() or ("", "", 0)
            return cert, tls_socket.version() or "", cipher, None


class TlsInspectSecurityTool:
    name = "tls_inspect"
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
        host, target_port, _scheme = parse_network_target(target, default_port=requested_port or DEFAULT_TLS_PORT)
        port = target_port or requested_port or DEFAULT_TLS_PORT
        timeout_seconds = normalize_timeout(arguments.get("timeout_seconds"))
        return SecurityToolInvocation(
            target=build_socket_target(host, port),
            timeout_seconds=timeout_seconds,
            protocol="tls",
            port=port,
            execution_args={"host": host, "port": port},
        )

    def execute(
        self,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult:
        host = str(invocation.execution_args["host"])
        port = int(invocation.execution_args["port"])
        verification_error: str | None = None
        try:
            cert, tls_version, cipher, _error = _handshake(
                host=host,
                port=port,
                timeout_seconds=invocation.timeout_seconds,
                verified=True,
            )
        except ssl.SSLCertVerificationError as exc:
            verification_error = str(exc)
            try:
                cert, tls_version, cipher, _error = _handshake(
                    host=host,
                    port=port,
                    timeout_seconds=invocation.timeout_seconds,
                    verified=False,
                )
            except Exception as fallback_exc:
                raise ValueError(f"tls_inspect failed: {fallback_exc}.") from fallback_exc
        except Exception as exc:
            raise ValueError(f"tls_inspect failed: {exc}.") from exc

        payload = {
            "host": host,
            "port": port,
            "tls_version": tls_version,
            "cipher": {
                "name": cipher[0],
                "protocol": cipher[1],
                "bits": cipher[2],
            },
            "certificate": {
                "subject": _normalize_name(cert.get("subject", ())),
                "issuer": _normalize_name(cert.get("issuer", ())),
                "subject_alt_names": [value for key, value in cert.get("subjectAltName", ()) if key == "DNS"],
                "not_before": _parse_cert_time(cert.get("notBefore")),
                "not_after": _parse_cert_time(cert.get("notAfter")),
                "serial_number": cert.get("serialNumber"),
            },
            "verification_error": verification_error,
        }
        summary = f"TLS inspection for {target.normalized_target} negotiated {tls_version or 'unknown TLS version'}."
        evidence = EvidenceCandidate(
            evidence_type="tls_certificate",
            target_ref=target.normalized_target,
            title=f"TLS inspection for {target.normalized_target}",
            summary=summary,
            content_type="application/json",
            payload=payload,
        )
        findings = _collect_findings(
            target_ref=target.normalized_target,
            cert=cert,
            verification_error=verification_error,
        )
        return SecurityToolResult(
            tool_name=self.name,
            target=target.normalized_target,
            summary=summary,
            payload=payload,
            evidence_candidates=[evidence],
            finding_candidates=findings,
        )
