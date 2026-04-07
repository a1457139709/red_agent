from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit
import re

from tools.contracts import normalize_port, require_non_empty_target

DEFAULT_HTTP_PORT = 80
DEFAULT_HTTPS_PORT = 443


def default_port_for_scheme(scheme: str | None) -> int | None:
    if scheme == "http":
        return DEFAULT_HTTP_PORT
    if scheme == "https":
        return DEFAULT_HTTPS_PORT
    return None


def parse_network_target(
    target: str,
    *,
    default_port: int | None = None,
) -> tuple[str, int | None, str | None]:
    normalized = require_non_empty_target(target)
    if "://" in normalized:
        parsed = urlsplit(normalized)
        if not parsed.hostname:
            raise ValueError("Target must include a valid host.")
        host = parsed.hostname
        scheme = parsed.scheme.lower() or None
        port = parsed.port or default_port_for_scheme(scheme) or default_port
        return host, port, scheme

    try:
        ip_address(normalized)
    except ValueError:
        pass
    else:
        return normalized, default_port, None

    if normalized.startswith("[") and "]" in normalized:
        parsed = urlsplit(f"//{normalized}")
        if not parsed.hostname:
            raise ValueError("Socket targets must look like host:port.")
        return parsed.hostname, parsed.port or default_port, None

    if normalized.count(":") == 1:
        parsed = urlsplit(f"//{normalized}")
        if parsed.hostname and parsed.port is not None:
            return parsed.hostname, parsed.port, None

    return normalized, default_port, None


def build_socket_target(host: str, port: int | None) -> str:
    if port is None:
        return host
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def normalize_header_mapping(headers: object | None) -> dict[str, str]:
    if headers in (None, ""):
        return {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be an object.")
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        normalized[str(key)] = str(value)
    return normalized


def normalize_positive_int(
    value: object | None,
    *,
    field_name: str,
    default: int,
    maximum: int,
) -> int:
    if value in (None, ""):
        return default
    port = normalize_port(value, field_name=field_name)
    assert port is not None
    if port > maximum:
        raise ValueError(f"{field_name} must be less than or equal to {maximum}.")
    return port


def decode_payload(payload: bytes, charset: str | None = None) -> str:
    candidates = []
    if charset:
        candidates.append(charset)
    candidates.extend(["utf-8", "utf-8-sig", "gb18030", "latin-1"])

    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def extract_charset(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = re.search(r"charset=([^\s;]+)", content_type, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip("\"'")


def truncate_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
