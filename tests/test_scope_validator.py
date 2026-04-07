from models.scope_policy import ScopePolicy
from orchestration.scope_validator import (
    AdditionalAdmissionTarget,
    AdmissionOutcome,
    AdmissionRequest,
    ScopeValidator,
)


def make_request(
    *,
    raw_target: str,
    tool_name: str = "http_probe",
    tool_category: str = "recon",
    protocol: str | None = None,
    port: int | None = None,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id="op-1",
        job_id="job-1",
        tool_name=tool_name,
        tool_category=tool_category,
        raw_target=raw_target,
        protocol=protocol,
        port=port,
    )


def make_policy(**kwargs) -> ScopePolicy:
    return ScopePolicy.create(operation_id="op-1", **kwargs)


def test_scope_validator_allows_exact_host_and_normalizes_https_default_port():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_hosts=["app.example.com"],
        allowed_ports=[443],
        allowed_protocols=["https"],
    )

    decision = validator.evaluate(policy, make_request(raw_target="https://app.example.com"))

    assert decision.outcome == AdmissionOutcome.ALLOWED
    assert decision.target.host == "app.example.com"
    assert decision.target.port == 443
    assert decision.target.protocol == "https"
    assert decision.target.normalized_target == "https://app.example.com"


def test_scope_validator_allows_subdomain_when_domain_is_in_scope():
    validator = ScopeValidator()
    policy = make_policy(allowed_domains=["example.com"])

    decision = validator.evaluate(policy, make_request(raw_target="api.internal.example.com"))

    assert decision.outcome == AdmissionOutcome.ALLOWED
    assert decision.target.host == "api.internal.example.com"


def test_scope_validator_denied_targets_override_other_allow_rules():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_domains=["example.com"],
        denied_targets=["admin.example.com"],
    )

    decision = validator.evaluate(policy, make_request(raw_target="https://admin.example.com"))

    assert decision.outcome == AdmissionOutcome.DENIED
    assert decision.reason_code == "target_denied"


def test_scope_validator_allows_explicit_ip_inside_cidr_scope():
    validator = ScopeValidator()
    policy = make_policy(allowed_cidrs=["10.0.0.0/24"])

    decision = validator.evaluate(policy, make_request(raw_target="10.0.0.25"))

    assert decision.outcome == AdmissionOutcome.ALLOWED
    assert decision.target.ip == "10.0.0.25"


def test_scope_validator_rejects_unknown_port_when_ports_are_restricted():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_domains=["example.com"],
        allowed_protocols=["tcp"],
        allowed_ports=[443],
    )

    decision = validator.evaluate(policy, make_request(raw_target="tcp://example.com"))

    assert decision.outcome == AdmissionOutcome.DENIED
    assert decision.reason_code == "port_not_allowed"


def test_scope_validator_rejects_disallowed_protocol_and_tool_category():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_domains=["example.com"],
        allowed_protocols=["https"],
        allowed_tool_categories=["recon"],
    )

    protocol_denied = validator.evaluate(policy, make_request(raw_target="http://example.com"))
    category_denied = validator.evaluate(
        policy,
        make_request(raw_target="https://example.com", tool_category="exploit"),
    )

    assert protocol_denied.outcome == AdmissionOutcome.DENIED
    assert protocol_denied.reason_code == "protocol_not_allowed"
    assert category_denied.outcome == AdmissionOutcome.DENIED
    assert category_denied.reason_code == "tool_category_not_allowed"


def test_scope_validator_rejects_malformed_target_before_execution():
    validator = ScopeValidator()
    policy = make_policy()

    decision = validator.evaluate(policy, make_request(raw_target="not a valid target/??"))

    assert decision.outcome == AdmissionOutcome.DENIED
    assert decision.reason_code == "target_parse_failed"


def test_scope_validator_marks_confirmation_required_for_tool_or_category():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_domains=["example.com"],
        confirmation_required_actions=["port_scan", "sensitive-recon"],
    )

    by_tool = validator.evaluate(
        policy,
        make_request(raw_target="example.com", tool_name="port_scan"),
    )
    by_category = validator.evaluate(
        policy,
        make_request(raw_target="example.com", tool_category="sensitive-recon"),
    )

    assert by_tool.outcome == AdmissionOutcome.REQUIRES_CONFIRMATION
    assert by_category.outcome == AdmissionOutcome.REQUIRES_CONFIRMATION


def test_scope_validator_checks_additional_targets_without_reconfirming():
    validator = ScopeValidator()
    policy = make_policy(
        allowed_domains=["example.com"],
        allowed_protocols=["dns"],
        allowed_ports=[53],
        confirmation_required_actions=["dns_lookup"],
    )
    request = AdmissionRequest(
        operation_id="op-1",
        job_id="job-1",
        tool_name="dns_lookup",
        tool_category="recon",
        raw_target="8.8.8.8",
        protocol="dns",
        port=53,
        additional_targets=(
            AdditionalAdmissionTarget(
                raw_target="outside.example.org",
                protocol="dns",
                port=53,
                label="query_name",
            ),
        ),
        skip_confirmation=True,
    )

    decision = validator.evaluate(policy, request)

    assert decision.outcome == AdmissionOutcome.DENIED
    assert decision.reason_code == "domain_out_of_scope"
    assert decision.message.startswith("query_name:")
