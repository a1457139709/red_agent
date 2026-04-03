from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

from models.scope_policy import ScopePolicy


def _normalize_host(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _normalize_protocol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _default_port_for_protocol(protocol: str | None) -> int | None:
    return {
        "http": 80,
        "https": 443,
    }.get(protocol)


def _coerce_port(value: int | str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Target port must be an integer.") from exc
    if port <= 0:
        raise ValueError("Target port must be greater than 0.")
    if port > 65535:
        raise ValueError("Target port must be less than 65536.")
    return port


def _is_ip_literal(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _normalize_target_literal(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Target is required.")
    if _is_ip_literal(stripped):
        return str(ip_address(stripped))
    return _normalize_host(stripped)


class AdmissionOutcome:
    ALLOWED = "allowed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class TargetDescriptor:
    raw_target: str
    kind: str
    host: str | None
    ip: str | None
    port: int | None
    protocol: str | None
    normalized_target: str


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    operation_id: str
    job_id: str | None
    tool_name: str
    tool_category: str
    raw_target: str
    protocol: str | None = None
    port: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    outcome: str
    reason_code: str | None
    message: str
    target: TargetDescriptor


class ScopeValidator:
    def describe_target(self, request: AdmissionRequest) -> TargetDescriptor:
        raw_target = request.raw_target.strip()
        if not raw_target:
            raise ValueError("Target is required.")

        requested_protocol = _normalize_protocol(request.protocol)
        requested_port = _coerce_port(request.port)

        if "://" in raw_target:
            parsed = urlsplit(raw_target)
            if not parsed.scheme or not parsed.hostname:
                raise ValueError("URL targets must include a valid scheme and host.")
            target_protocol = _normalize_protocol(parsed.scheme)
            target_port = parsed.port or _default_port_for_protocol(target_protocol)
            return self._build_descriptor(
                kind="url",
                raw_target=raw_target,
                host=parsed.hostname,
                protocol=target_protocol,
                port=target_port,
                requested_protocol=requested_protocol,
                requested_port=requested_port,
            )

        if "/" in raw_target or "?" in raw_target or "#" in raw_target:
            raise ValueError("Target must be a hostname, IP, host:port, or URL.")

        if _is_ip_literal(raw_target):
            return self._build_descriptor(
                kind="ip",
                raw_target=raw_target,
                host=raw_target,
                protocol=requested_protocol,
                port=requested_port,
                requested_protocol=requested_protocol,
                requested_port=requested_port,
            )

        if ":" in raw_target:
            parsed = urlsplit(f"//{raw_target}")
            if not parsed.hostname or parsed.port is None:
                raise ValueError("Socket targets must look like host:port.")
            return self._build_descriptor(
                kind="socket",
                raw_target=raw_target,
                host=parsed.hostname,
                protocol=requested_protocol,
                port=parsed.port,
                requested_protocol=requested_protocol,
                requested_port=requested_port,
            )

        return self._build_descriptor(
            kind="host",
            raw_target=raw_target,
            host=raw_target,
            protocol=requested_protocol,
            port=requested_port,
            requested_protocol=requested_protocol,
            requested_port=requested_port,
        )

    def evaluate(self, policy: ScopePolicy, request: AdmissionRequest) -> AdmissionDecision:
        try:
            target = self.describe_target(request)
        except ValueError as exc:
            fallback_target = TargetDescriptor(
                raw_target=request.raw_target,
                kind="unknown",
                host=None,
                ip=None,
                port=request.port,
                protocol=_normalize_protocol(request.protocol),
                normalized_target=request.raw_target.strip() or request.raw_target,
            )
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="target_parse_failed",
                message=f"Target is invalid: {exc}",
                target=fallback_target,
            )

        denied_target = self._find_matching_denied_target(policy, target)
        if denied_target is not None:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="target_denied",
                message=f"Target '{denied_target}' is explicitly denied by the scope policy.",
                target=target,
            )

        scope_denial = self._check_scope(policy, target)
        if scope_denial is not None:
            return scope_denial

        protocol_denial = self._check_protocol(policy, target)
        if protocol_denial is not None:
            return protocol_denial

        port_denial = self._check_port(policy, target)
        if port_denial is not None:
            return port_denial

        tool_category_denial = self._check_tool_category(policy, request, target)
        if tool_category_denial is not None:
            return tool_category_denial

        if request.tool_name in policy.confirmation_required_actions:
            return AdmissionDecision(
                outcome=AdmissionOutcome.REQUIRES_CONFIRMATION,
                reason_code=None,
                message=f"Tool '{request.tool_name}' requires operator confirmation.",
                target=target,
            )
        if request.tool_category in policy.confirmation_required_actions:
            return AdmissionDecision(
                outcome=AdmissionOutcome.REQUIRES_CONFIRMATION,
                reason_code=None,
                message=f"Tool category '{request.tool_category}' requires operator confirmation.",
                target=target,
            )

        return AdmissionDecision(
            outcome=AdmissionOutcome.ALLOWED,
            reason_code=None,
            message="Target is within the declared scope policy.",
            target=target,
        )

    def _build_descriptor(
        self,
        *,
        kind: str,
        raw_target: str,
        host: str,
        protocol: str | None,
        port: int | None,
        requested_protocol: str | None,
        requested_port: int | None,
    ) -> TargetDescriptor:
        normalized_host = _normalize_target_literal(host)
        is_ip = _is_ip_literal(normalized_host)
        effective_protocol = protocol
        effective_port = port

        if requested_protocol is not None:
            if effective_protocol is not None and effective_protocol != requested_protocol:
                raise ValueError("Requested protocol does not match the target.")
            effective_protocol = requested_protocol
        if requested_port is not None:
            if effective_port is not None and effective_port != requested_port:
                raise ValueError("Requested port does not match the target.")
            effective_port = requested_port

        if kind == "url":
            normalized_target = f"{effective_protocol}://{normalized_host}"
            if effective_port is not None:
                default_port = _default_port_for_protocol(effective_protocol)
                if default_port != effective_port:
                    normalized_target = f"{normalized_target}:{effective_port}"
        else:
            normalized_target = normalized_host
            if effective_port is not None:
                if ":" in normalized_host and not normalized_host.startswith("["):
                    normalized_target = f"[{normalized_host}]"
                normalized_target = f"{normalized_target}:{effective_port}"

        return TargetDescriptor(
            raw_target=raw_target,
            kind=kind,
            host=normalized_host,
            ip=normalized_host if is_ip else None,
            port=effective_port,
            protocol=effective_protocol,
            normalized_target=normalized_target,
        )

    def _find_matching_denied_target(self, policy: ScopePolicy, target: TargetDescriptor) -> str | None:
        candidates = {target.normalized_target.lower()}
        if target.host is not None:
            candidates.add(target.host.lower())
        if target.ip is not None:
            candidates.add(target.ip)
        if "://" not in target.raw_target and "/" not in target.raw_target and "?" not in target.raw_target:
            candidates.add(_normalize_target_literal(target.raw_target))
        else:
            candidates.add(target.raw_target.strip().lower())

        for denied_target in policy.denied_targets:
            denied = denied_target.strip()
            if not denied:
                continue
            normalized_denied = denied.lower()
            if normalized_denied in candidates:
                return denied_target
            try:
                if _normalize_target_literal(denied) in candidates:
                    return denied_target
            except ValueError:
                continue
        return None

    def _check_scope(self, policy: ScopePolicy, target: TargetDescriptor) -> AdmissionDecision | None:
        if target.ip is not None:
            host_allowed = self._matches_allowed_hosts(policy, target.host)
            cidr_allowed = self._matches_allowed_cidrs(policy, target.ip)
            if host_allowed or cidr_allowed:
                return None
            if policy.allowed_cidrs:
                return AdmissionDecision(
                    outcome=AdmissionOutcome.DENIED,
                    reason_code="cidr_out_of_scope",
                    message=f"IP target '{target.ip}' is outside the allowed CIDR ranges.",
                    target=target,
                )
            if policy.allowed_hosts:
                return AdmissionDecision(
                    outcome=AdmissionOutcome.DENIED,
                    reason_code="host_out_of_scope",
                    message=f"Target host '{target.host}' is outside the allowed hosts list.",
                    target=target,
                )
            return None

        if self._matches_allowed_hosts(policy, target.host):
            return None
        if self._matches_allowed_domains(policy, target.host):
            return None
        if policy.allowed_hosts:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="host_out_of_scope",
                message=f"Target host '{target.host}' is outside the allowed hosts list.",
                target=target,
            )
        if policy.allowed_domains:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="domain_out_of_scope",
                message=f"Target host '{target.host}' is outside the allowed domains.",
                target=target,
            )
        if policy.allowed_cidrs:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="cidr_out_of_scope",
                message="CIDR scope only applies to explicit IP targets; hostname targets are not expanded.",
                target=target,
            )
        return None

    def _check_protocol(self, policy: ScopePolicy, target: TargetDescriptor) -> AdmissionDecision | None:
        if not policy.allowed_protocols:
            return None
        if target.protocol is None:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="protocol_not_allowed",
                message="Target protocol is unknown and cannot be matched against the scope policy.",
                target=target,
            )
        allowed_protocols = {_normalize_protocol(protocol) for protocol in policy.allowed_protocols}
        if target.protocol in allowed_protocols:
            return None
        return AdmissionDecision(
            outcome=AdmissionOutcome.DENIED,
            reason_code="protocol_not_allowed",
            message=f"Protocol '{target.protocol}' is not allowed by the scope policy.",
            target=target,
        )

    def _check_port(self, policy: ScopePolicy, target: TargetDescriptor) -> AdmissionDecision | None:
        if not policy.allowed_ports:
            return None
        if target.port is None:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="port_not_allowed",
                message="Target port is unknown and cannot be matched against the scope policy.",
                target=target,
            )
        if target.port in policy.allowed_ports:
            return None
        return AdmissionDecision(
            outcome=AdmissionOutcome.DENIED,
            reason_code="port_not_allowed",
            message=f"Port '{target.port}' is not allowed by the scope policy.",
            target=target,
        )

    def _check_tool_category(
        self,
        policy: ScopePolicy,
        request: AdmissionRequest,
        target: TargetDescriptor,
    ) -> AdmissionDecision | None:
        if not policy.allowed_tool_categories:
            return None
        allowed_tool_categories = {
            category.strip().lower()
            for category in policy.allowed_tool_categories
            if category.strip()
        }
        if request.tool_category.strip().lower() in allowed_tool_categories:
            return None
        return AdmissionDecision(
            outcome=AdmissionOutcome.DENIED,
            reason_code="tool_category_not_allowed",
            message=f"Tool category '{request.tool_category}' is not allowed by the scope policy.",
            target=target,
        )

    def _matches_allowed_hosts(self, policy: ScopePolicy, host: str | None) -> bool:
        if host is None or not policy.allowed_hosts:
            return False
        normalized_allowed = {_normalize_target_literal(value) for value in policy.allowed_hosts if value.strip()}
        return host in normalized_allowed

    def _matches_allowed_domains(self, policy: ScopePolicy, host: str | None) -> bool:
        if host is None or not policy.allowed_domains or _is_ip_literal(host):
            return False
        normalized_host = _normalize_host(host)
        for domain in policy.allowed_domains:
            normalized_domain = _normalize_host(domain)
            if normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}"):
                return True
        return False

    def _matches_allowed_cidrs(self, policy: ScopePolicy, ip_literal: str) -> bool:
        if not policy.allowed_cidrs:
            return False
        target_ip = ip_address(ip_literal)
        for cidr in policy.allowed_cidrs:
            if target_ip in ip_network(cidr, strict=False):
                return True
        return False
