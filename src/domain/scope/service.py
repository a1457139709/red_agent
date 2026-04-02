from __future__ import annotations

import ipaddress

from domain.operations import ScopePolicy
from storage.repositories import ScopePolicyRepository

from .types import ScopeDecision
from .validators import (
    validate_cidr,
    validate_domain,
    validate_hostname,
    validate_ip,
    validate_port,
    validate_protocol,
)


class ScopePolicyService:
    def __init__(self, repository: ScopePolicyRepository) -> None:
        self.repository = repository

    def upsert_policy(self, policy: ScopePolicy) -> ScopePolicy:
        decision = self.validate_policy(policy)
        if not decision.allowed:
            raise ValueError(decision.message)
        return self.repository.upsert(policy)

    def get_policy(self, operation_id: str) -> ScopePolicy | None:
        return self.repository.get_by_operation_id(operation_id)

    def delete_policy(self, operation_id: str) -> None:
        self.repository.delete_by_operation_id(operation_id)

    def validate_policy(self, policy: ScopePolicy) -> ScopeDecision:
        try:
            allowed_hostnames = [validate_hostname(value) for value in policy.allowed_hostnames]
            allowed_ips = [validate_ip(value) for value in policy.allowed_ips]
            allowed_domains = [validate_domain(value) for value in policy.allowed_domains]
            allowed_cidrs = [validate_cidr(value) for value in policy.allowed_cidrs]
            allowed_ports = [validate_port(value) for value in policy.allowed_ports]
            allowed_protocols = [validate_protocol(value) for value in policy.allowed_protocols]
        except ValueError as exc:
            return ScopeDecision.deny("invalid_policy", str(exc))

        if not (allowed_hostnames or allowed_ips or allowed_domains or allowed_cidrs):
            return ScopeDecision.deny(
                "missing_target_scope",
                "Scope policy must declare at least one allowed hostname, IP, domain, or CIDR",
            )
        if not allowed_protocols:
            return ScopeDecision.deny(
                "missing_protocol_scope",
                "Scope policy must declare at least one allowed protocol",
            )
        if not policy.allowed_tool_categories:
            return ScopeDecision.deny(
                "missing_tool_scope",
                "Scope policy must declare at least one allowed tool category",
            )
        if policy.max_concurrency < 1:
            return ScopeDecision.deny(
                "invalid_policy",
                "Scope policy max_concurrency must be at least 1",
            )
        return ScopeDecision.allow("Scope policy is valid")

    def check_target(
        self,
        policy: ScopePolicy,
        *,
        hostname: str | None = None,
        ip: str | None = None,
        domain: str | None = None,
        cidr: str | None = None,
        port: int | None = None,
        protocol: str | None = None,
    ) -> ScopeDecision:
        validation = self.validate_policy(policy)
        if not validation.allowed:
            return validation

        if not any(value is not None for value in (hostname, ip, domain, cidr, port, protocol)):
            return ScopeDecision.deny("missing_target", "At least one target attribute is required")

        normalized_hostname = validate_hostname(hostname) if hostname is not None else None
        normalized_ip = validate_ip(ip) if ip is not None else None
        normalized_domain = validate_domain(domain) if domain is not None else None
        normalized_cidr = validate_cidr(cidr) if cidr is not None else None
        normalized_port = validate_port(port) if port is not None else None
        normalized_protocol = validate_protocol(protocol) if protocol is not None else None

        for candidate in (normalized_hostname, normalized_ip, normalized_domain, normalized_cidr):
            if candidate is not None and candidate in policy.denied_targets:
                return ScopeDecision.deny(
                    "target_denied",
                    f"Target {candidate} is explicitly denied by scope policy",
                )

        if normalized_hostname is not None and normalized_hostname not in policy.allowed_hostnames:
            return ScopeDecision.deny(
                "hostname_not_allowed",
                f"Hostname {normalized_hostname} is not allowed by scope policy",
            )
        if normalized_ip is not None and not self._is_ip_allowed(policy, normalized_ip):
            return ScopeDecision.deny(
                "ip_not_allowed",
                f"IP {normalized_ip} is not allowed by scope policy",
            )
        if normalized_domain is not None and normalized_domain not in policy.allowed_domains:
            return ScopeDecision.deny(
                "domain_not_allowed",
                f"Domain {normalized_domain} is not allowed by scope policy",
            )
        if normalized_cidr is not None and normalized_cidr not in policy.allowed_cidrs:
            return ScopeDecision.deny(
                "cidr_not_allowed",
                f"CIDR {normalized_cidr} is not allowed by scope policy",
            )
        if normalized_port is not None and normalized_port not in policy.allowed_ports:
            return ScopeDecision.deny(
                "port_not_allowed",
                f"Port {normalized_port} is not allowed by scope policy",
            )
        if normalized_protocol is not None and normalized_protocol not in policy.allowed_protocols:
            return ScopeDecision.deny(
                "protocol_not_allowed",
                f"Protocol {normalized_protocol} is not allowed by scope policy",
            )

        return ScopeDecision.allow()

    def _is_ip_allowed(self, policy: ScopePolicy, ip: str) -> bool:
        if ip in policy.allowed_ips:
            return True
        ip_value = ipaddress.ip_address(ip)
        for network in policy.allowed_cidrs:
            if ip_value in ipaddress.ip_network(network, strict=False):
                return True
        return False
