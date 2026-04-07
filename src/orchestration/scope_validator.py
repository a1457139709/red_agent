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
    additional_targets: tuple["AdditionalAdmissionTarget", ...] = ()
    skip_confirmation: bool = False
    admission_stage: str = "initial"


@dataclass(frozen=True, slots=True)
class AdditionalAdmissionTarget:
    raw_target: str
    protocol: str | None = None
    port: int | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    outcome: str
    reason_code: str | None
    message: str
    target: TargetDescriptor


@dataclass(frozen=True, slots=True)
class _TargetEvaluation:
    target: TargetDescriptor | None
    decision: AdmissionDecision | None


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
        primary_evaluation = self._evaluate_target_constraints(
            policy=policy,
            request=request,
            raw_target=request.raw_target,
            protocol=request.protocol,
            port=request.port,
        )
        if primary_evaluation.decision is not None:
            return primary_evaluation.decision
        target = primary_evaluation.target
        assert target is not None

        for additional_target in request.additional_targets:
            evaluation = self._evaluate_target_constraints(
                policy=policy,
                request=request,
                raw_target=additional_target.raw_target,
                protocol=additional_target.protocol,
                port=additional_target.port,
                label=additional_target.label,
            )
            if evaluation.decision is not None:
                return evaluation.decision

        tool_category_denial = self._check_tool_category(policy, request, target)
        if tool_category_denial is not None:
            return tool_category_denial

        if not request.skip_confirmation and request.tool_name in policy.confirmation_required_actions:
            return AdmissionDecision(
                outcome=AdmissionOutcome.REQUIRES_CONFIRMATION,
                reason_code=None,
                message=f"Tool '{request.tool_name}' requires operator confirmation.",
                target=target,
            )
        if not request.skip_confirmation and request.tool_category in policy.confirmation_required_actions:
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

    def _evaluate_target_constraints(
        self,
        *,
        policy: ScopePolicy,
        request: AdmissionRequest,
        raw_target: str,
        protocol: str | None,
        port: int | None,
        label: str | None = None,
    ) -> _TargetEvaluation:
        scoped_request = AdmissionRequest(
            operation_id=request.operation_id,
            job_id=request.job_id,
            tool_name=request.tool_name,
            tool_category=request.tool_category,
            raw_target=raw_target,
            protocol=protocol,
            port=port,
            metadata=request.metadata,
            skip_confirmation=True,
        )
        try:
            target = self.describe_target(scoped_request)
        except ValueError as exc:
            fallback_target = TargetDescriptor(
                raw_target=raw_target,
                kind="unknown",
                host=None,
                ip=None,
                port=port,
                protocol=_normalize_protocol(protocol),
                normalized_target=raw_target.strip() or raw_target,
            )
            return _TargetEvaluation(
                target=None,
                decision=AdmissionDecision(
                    outcome=AdmissionOutcome.DENIED,
                    reason_code="target_parse_failed",
                    message=self._format_target_message(label, f"Target is invalid: {exc}"),
                    target=fallback_target,
                ),
            )

        denied_target = self._find_matching_denied_target(policy, target)
        if denied_target is not None:
            return _TargetEvaluation(
                target=None,
                decision=AdmissionDecision(
                    outcome=AdmissionOutcome.DENIED,
                    reason_code="target_denied",
                    message=self._format_target_message(
                        label,
                        f"Target '{denied_target}' is explicitly denied by the scope policy.",
                    ),
                    target=target,
                ),
            )

        for denial in (
            self._check_scope(policy, target),
            self._check_protocol(policy, target),
            self._check_port(policy, scoped_request, target),
        ):
            if denial is not None:
                return _TargetEvaluation(
                    target=None,
                    decision=AdmissionDecision(
                        outcome=denial.outcome,
                        reason_code=denial.reason_code,
                        message=self._format_target_message(label, denial.message),
                        target=denial.target,
                    ),
                )

        return _TargetEvaluation(target=target, decision=None)

    def _format_target_message(self, label: str | None, message: str) -> str:
        if not label:
            return message
        return f"{label}: {message}"

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

    def _check_port(
        self,
        policy: ScopePolicy,
        request: AdmissionRequest,
        target: TargetDescriptor,
    ) -> AdmissionDecision | None:
        if not policy.allowed_ports:
            return None
        requested_ports: list[int] = []
        raw_ports = self._extract_metadata_ports(request)
        if raw_ports:
            requested_ports = raw_ports
        elif target.port is not None:
            requested_ports = [target.port]

        if not requested_ports:
            return AdmissionDecision(
                outcome=AdmissionOutcome.DENIED,
                reason_code="port_not_allowed",
                message="Target port is unknown and cannot be matched against the scope policy.",
                target=target,
            )
        disallowed_ports = [port for port in requested_ports if port not in policy.allowed_ports]
        if not disallowed_ports:
            return None
        if len(disallowed_ports) == 1:
            message = f"Port '{disallowed_ports[0]}' is not allowed by the scope policy."
        else:
            ports_text = ", ".join(str(port) for port in disallowed_ports)
            message = f"Ports '{ports_text}' are not allowed by the scope policy."
        return AdmissionDecision(
            outcome=AdmissionOutcome.DENIED,
            reason_code="port_not_allowed",
            message=message,
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

    def _extract_metadata_ports(
        self,
        request: AdmissionRequest,
    ) -> list[int]:
        raw_ports = request.metadata.get("ports")
        if not isinstance(raw_ports, list):
            return []
        ports: list[int] = []
        for raw_port in raw_ports:
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                continue
            if port > 0:
                ports.append(port)
        return ports
