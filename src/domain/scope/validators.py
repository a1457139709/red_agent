from __future__ import annotations

import ipaddress
import re


HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9.-]+(?<!-)$")
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
ALLOWED_PROTOCOLS = frozenset({"tcp", "udp", "http", "https", "dns", "tls"})


def validate_hostname(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Hostname cannot be empty")
    if not HOSTNAME_RE.fullmatch(candidate):
        raise ValueError(f"Invalid hostname: {value}")
    return candidate.lower()


def validate_ip(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("IP cannot be empty")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError as exc:
        raise ValueError(f"Invalid IP: {value}") from exc


def validate_domain(value: str) -> str:
    candidate = value.strip().lower()
    if not candidate:
        raise ValueError("Domain cannot be empty")
    if not DOMAIN_RE.fullmatch(candidate):
        raise ValueError(f"Invalid domain: {value}")
    return candidate


def validate_cidr(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("CIDR cannot be empty")
    try:
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid CIDR: {value}") from exc
    return str(network)


def validate_port(value: int) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Invalid port: {value}")
    if value < 1 or value > 65535:
        raise ValueError(f"Invalid port: {value}")
    return value


def validate_protocol(value: str) -> str:
    candidate = value.strip().lower()
    if candidate not in ALLOWED_PROTOCOLS:
        raise ValueError(f"Invalid protocol: {value}")
    return candidate
