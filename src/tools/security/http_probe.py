from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import re

from models.scope_policy import ScopePolicy
from orchestration.scope_validator import TargetDescriptor
from tools.contracts import (
    EvidenceCandidate,
    SecurityToolInvocation,
    SecurityToolResult,
    normalize_timeout,
    require_non_empty_target,
)

from ._common import decode_payload, extract_charset, normalize_header_mapping

DEFAULT_MAX_BODY_CHARS = 1024
MAX_BODY_CHARS = 8192
USER_AGENT = "red-code/0.1 (+security-tool)"
ALLOWED_METHODS = {"GET", "HEAD"}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _normalize_method(value: object | None) -> str:
    if value in (None, ""):
        return "GET"
    method = str(value).strip().upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"method must be one of: {', '.join(sorted(ALLOWED_METHODS))}.")
    return method


def _normalize_max_body_chars(value: object | None) -> int:
    if value in (None, ""):
        return DEFAULT_MAX_BODY_CHARS
    try:
        max_body_chars = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_body_chars must be an integer.") from exc
    if max_body_chars <= 0:
        raise ValueError("max_body_chars must be greater than 0.")
    if max_body_chars > MAX_BODY_CHARS:
        raise ValueError(f"max_body_chars must be less than or equal to {MAX_BODY_CHARS}.")
    return max_body_chars


def _normalize_body_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[^\S\n]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


class HttpProbeSecurityTool:
    name = "http_probe"
    category = "recon"

    def validate_invocation(
        self,
        *,
        target: str,
        arguments: Mapping[str, Any],
        policy: ScopePolicy,
    ) -> SecurityToolInvocation:
        del policy
        url = require_non_empty_target(target)
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("http_probe target must be an absolute http(s) URL.")
        method = _normalize_method(arguments.get("method"))
        timeout_seconds = normalize_timeout(arguments.get("timeout_seconds"))
        max_body_chars = _normalize_max_body_chars(arguments.get("max_body_chars"))
        headers = normalize_header_mapping(arguments.get("headers"))

        return SecurityToolInvocation(
            target=url,
            timeout_seconds=timeout_seconds,
            protocol=parsed.scheme.lower(),
            port=parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
            metadata={"method": method},
            execution_args={
                "method": method,
                "max_body_chars": max_body_chars,
                "headers": headers,
            },
        )

    def execute(
        self,
        invocation: SecurityToolInvocation,
        target: TargetDescriptor,
    ) -> SecurityToolResult:
        method = str(invocation.execution_args["method"])
        max_body_chars = int(invocation.execution_args["max_body_chars"])
        headers = {"User-Agent": USER_AGENT, **dict(invocation.execution_args["headers"])}
        request = Request(invocation.target, headers=headers, method=method)
        opener = build_opener(_NoRedirectHandler)

        response = None
        body = b""
        error_message: str | None = None
        try:
            response = opener.open(request, timeout=invocation.timeout_seconds)
            with response:
                body = response.read(max_body_chars + 1)
        except HTTPError as exc:
            response = exc
            body = exc.read(max_body_chars + 1)
        except URLError as exc:
            raise ValueError(f"http_probe failed: {exc.reason}.") from exc
        except Exception as exc:
            raise ValueError(f"http_probe failed: {exc}.") from exc

        content_type = response.headers.get("Content-Type", "")
        decoded = decode_payload(body, extract_charset(content_type))
        normalized_body = _normalize_body_text(decoded)
        truncated = len(normalized_body) > max_body_chars or len(body) > max_body_chars
        body_snippet = normalized_body[:max_body_chars]
        if truncated and body_snippet:
            body_snippet += "..."

        status_code = getattr(response, "status", None) or getattr(response, "code", None) or 200
        final_url = response.geturl() or invocation.target
        location = response.headers.get("Location")
        if 300 <= status_code < 400:
            final_url = invocation.target
        if status_code >= 400:
            error_message = f"HTTP {status_code}"

        payload = {
            "requested_url": invocation.target,
            "final_url": final_url,
            "status_code": status_code,
            "method": method,
            "headers": dict(response.headers.items()),
            "location": location,
            "content_type": content_type,
            "body_snippet": body_snippet,
            "body_truncated": truncated,
            "error": error_message,
        }
        summary = (
            f"HTTP {method} {target.normalized_target} returned {status_code} "
            f"from {final_url}."
        )
        evidence = EvidenceCandidate(
            evidence_type="http_response",
            target_ref=final_url,
            title=f"HTTP probe {status_code} for {final_url}",
            summary=summary,
            content_type=content_type or "text/plain",
            payload=payload,
        )
        return SecurityToolResult(
            tool_name=self.name,
            target=final_url,
            summary=summary,
            payload=payload,
            evidence_candidates=[evidence],
        )
