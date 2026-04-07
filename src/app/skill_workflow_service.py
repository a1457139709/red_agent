from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import Any
from urllib.parse import SplitResult, urlsplit

from agent.settings import Settings, get_settings
from models.job import Job
from models.operation import Operation
from models.scope_policy import ScopePolicy
from models.skill import LoadedSkill
from orchestration.scope_validator import AdmissionOutcome, AdmissionRequest, ScopeValidator
from tools import build_security_tool_registry
from tools.executor import SecurityToolExecutionError, SecurityToolExecutor

from .job_service import JobService
from .operation_service import OperationService


DEFAULT_HTTP_PATHS = ("/", "/robots.txt", "/.well-known/security.txt")
DEFAULT_HTTP_METHOD = "GET"


@dataclass(frozen=True, slots=True)
class SkillWorkflowJobTemplate:
    job_type: str
    target_ref: str
    arguments: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = None
    retry_limit: int = 0
    summary: str = ""
    requires_confirmation: bool = False
    admission_message: str | None = None

    def effective_arguments(self) -> dict[str, Any]:
        return dict(self.arguments)


@dataclass(frozen=True, slots=True)
class SkillWorkflowSkippedJob:
    job_type: str
    target_ref: str
    reason: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class SkillWorkflowPlan:
    skill_name: str
    workflow_profile: str
    operation: Operation
    primary_target: str
    planned_jobs: list[SkillWorkflowJobTemplate]
    skipped_jobs: list[SkillWorkflowSkippedJob]


@dataclass(frozen=True, slots=True)
class _WorkflowTarget:
    raw_target: str
    host: str
    is_url: bool
    is_ip_literal: bool
    scheme: str | None = None
    port: int | None = None
    base_url: str | None = None


class SkillWorkflowService:
    def __init__(
        self,
        *,
        job_service: JobService,
        operation_service: OperationService,
        security_tool_executor: SecurityToolExecutor,
        scope_validator: ScopeValidator,
    ) -> None:
        self.job_service = job_service
        self.operation_service = operation_service
        self.security_tool_executor = security_tool_executor
        self.scope_validator = scope_validator

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SkillWorkflowService":
        settings = settings or get_settings()
        return cls(
            job_service=JobService.from_settings(settings),
            operation_service=OperationService.from_settings(settings),
            security_tool_executor=SecurityToolExecutor(build_security_tool_registry()),
            scope_validator=ScopeValidator(),
        )

    def plan_workflow(
        self,
        *,
        skill: LoadedSkill,
        operation_identifier: str,
        primary_target: str,
        overrides: Mapping[str, Any] | None = None,
    ) -> SkillWorkflowPlan:
        workflow_profile = skill.manifest.workflow_profile
        if not workflow_profile:
            raise ValueError(f"Skill '{skill.manifest.name}' does not define a workflow profile.")
        normalized_target = primary_target.strip()
        if not normalized_target:
            raise ValueError("Primary target is required.")
        operation = self.operation_service.require_operation(operation_identifier)
        policy = self.operation_service.require_scope_policy(operation.id)
        templates = self._build_templates(
            workflow_profile=workflow_profile,
            primary_target=normalized_target,
            overrides=dict(overrides or {}),
        )
        planned_jobs, skipped_jobs = self._filter_templates(
            operation=operation,
            policy=policy,
            templates=templates,
        )
        if not planned_jobs:
            raise ValueError(
                f"Skill workflow '{skill.manifest.name}' produced no in-scope jobs for operation "
                f"{operation.public_id or operation.id}."
            )
        return SkillWorkflowPlan(
            skill_name=skill.manifest.name,
            workflow_profile=workflow_profile,
            operation=operation,
            primary_target=normalized_target,
            planned_jobs=planned_jobs,
            skipped_jobs=skipped_jobs,
        )

    def apply_plan(self, plan: SkillWorkflowPlan) -> list[Job]:
        created_jobs: list[Job] = []
        for template in plan.planned_jobs:
            created_jobs.append(
                self.job_service.create_job(
                    operation_identifier=plan.operation.id,
                    job_type=template.job_type,
                    target_ref=template.target_ref,
                    arguments=template.effective_arguments(),
                    timeout_seconds=template.timeout_seconds,
                    retry_limit=template.retry_limit,
                )
            )
        return created_jobs

    def _build_templates(
        self,
        *,
        workflow_profile: str,
        primary_target: str,
        overrides: dict[str, Any],
    ) -> list[SkillWorkflowJobTemplate]:
        if workflow_profile == "surface-recon":
            return self._build_surface_recon(primary_target=primary_target, overrides=overrides)
        if workflow_profile == "web-enum":
            return self._build_web_enum(primary_target=primary_target, overrides=overrides)
        raise ValueError(f"Unsupported workflow profile: {workflow_profile}")

    def _filter_templates(
        self,
        *,
        operation: Operation,
        policy: ScopePolicy,
        templates: list[SkillWorkflowJobTemplate],
    ) -> tuple[list[SkillWorkflowJobTemplate], list[SkillWorkflowSkippedJob]]:
        planned_jobs: list[SkillWorkflowJobTemplate] = []
        skipped_jobs: list[SkillWorkflowSkippedJob] = []
        for template in templates:
            try:
                tool = self.security_tool_executor.get_tool(template.job_type)
                invocation = self.security_tool_executor.validate(
                    template.job_type,
                    target=template.target_ref,
                    arguments=self._effective_arguments(template),
                    policy=policy,
                )
                decision = self.scope_validator.evaluate(
                    policy,
                    invocation.to_admission_request(
                        operation_id=operation.id,
                        job_id=None,
                        tool_name=tool.name,
                        tool_category=tool.category,
                    ),
                )
            except SecurityToolExecutionError as exc:
                skipped_jobs.append(
                    SkillWorkflowSkippedJob(
                        job_type=template.job_type,
                        target_ref=template.target_ref,
                        reason=exc.error,
                        summary=template.summary,
                    )
                )
                continue

            if decision.outcome == AdmissionOutcome.DENIED:
                skipped_jobs.append(
                    SkillWorkflowSkippedJob(
                        job_type=template.job_type,
                        target_ref=template.target_ref,
                        reason=decision.message,
                        summary=template.summary,
                    )
                )
                continue

            planned_jobs.append(
                SkillWorkflowJobTemplate(
                    job_type=template.job_type,
                    target_ref=template.target_ref,
                    arguments=template.effective_arguments(),
                    timeout_seconds=template.timeout_seconds,
                    retry_limit=template.retry_limit,
                    summary=template.summary,
                    requires_confirmation=decision.outcome == AdmissionOutcome.REQUIRES_CONFIRMATION,
                    admission_message=decision.message,
                )
            )
        return planned_jobs, skipped_jobs

    def _effective_arguments(self, template: SkillWorkflowJobTemplate) -> dict[str, Any]:
        arguments = template.effective_arguments()
        if template.timeout_seconds is not None:
            arguments["timeout_seconds"] = template.timeout_seconds
        return arguments

    def _build_surface_recon(
        self,
        *,
        primary_target: str,
        overrides: dict[str, Any],
    ) -> list[SkillWorkflowJobTemplate]:
        target = self._parse_primary_target(primary_target)
        timeout_seconds = _coerce_optional_positive_int(overrides.get("timeout_seconds"))
        retry_limit = _coerce_non_negative_int(overrides.get("retry_limit"), default=0)
        include_dns = _coerce_bool(overrides.get("include_dns"), default=True)
        include_http = _coerce_bool(overrides.get("include_http"), default=True)
        include_tls = _coerce_bool(overrides.get("include_tls"), default=True)
        http_method = str(overrides.get("http_method", DEFAULT_HTTP_METHOD)).strip().upper() or DEFAULT_HTTP_METHOD
        max_body_chars = overrides.get("max_body_chars")
        nameserver = overrides.get("nameserver")

        templates: list[SkillWorkflowJobTemplate] = []
        if include_dns and not target.is_ip_literal:
            arguments: dict[str, Any] = {"record_type": "A"}
            if nameserver not in (None, ""):
                arguments["nameserver"] = str(nameserver).strip()
            templates.append(
                SkillWorkflowJobTemplate(
                    job_type="dns_lookup",
                    target_ref=target.host,
                    arguments=arguments,
                    timeout_seconds=timeout_seconds,
                    retry_limit=retry_limit,
                    summary=f"Resolve DNS records for {target.host}.",
                )
            )

        if include_http:
            for probe_url in self._derive_probe_urls(target):
                http_arguments: dict[str, Any] = {"method": http_method}
                if max_body_chars not in (None, ""):
                    http_arguments["max_body_chars"] = max_body_chars
                templates.append(
                    SkillWorkflowJobTemplate(
                        job_type="http_probe",
                        target_ref=probe_url,
                        arguments=http_arguments,
                        timeout_seconds=timeout_seconds,
                        retry_limit=retry_limit,
                        summary=f"Probe {probe_url}.",
                    )
                )

        if include_tls:
            tls_target = self._derive_tls_target(target)
            if tls_target is not None:
                templates.append(
                    SkillWorkflowJobTemplate(
                        job_type="tls_inspect",
                        target_ref=tls_target,
                        arguments={},
                        timeout_seconds=timeout_seconds,
                        retry_limit=retry_limit,
                        summary=f"Inspect TLS for {tls_target}.",
                    )
                )

        return _dedupe_templates(templates)

    def _build_web_enum(
        self,
        *,
        primary_target: str,
        overrides: dict[str, Any],
    ) -> list[SkillWorkflowJobTemplate]:
        target = self._parse_primary_target(primary_target)
        timeout_seconds = _coerce_optional_positive_int(overrides.get("timeout_seconds"))
        retry_limit = _coerce_non_negative_int(overrides.get("retry_limit"), default=0)
        include_tls = _coerce_bool(overrides.get("include_tls"), default=True)
        http_method = str(overrides.get("http_method", DEFAULT_HTTP_METHOD)).strip().upper() or DEFAULT_HTTP_METHOD
        max_body_chars = overrides.get("max_body_chars")
        paths = _coerce_path_list(overrides.get("paths"), default=DEFAULT_HTTP_PATHS)

        templates: list[SkillWorkflowJobTemplate] = []
        base_urls = self._derive_probe_urls(target)
        seen_tls_targets: set[str] = set()
        for base_url in base_urls:
            for path in paths:
                probe_url = _join_url_path(base_url, path)
                http_arguments: dict[str, Any] = {"method": http_method}
                if max_body_chars not in (None, ""):
                    http_arguments["max_body_chars"] = max_body_chars
                templates.append(
                    SkillWorkflowJobTemplate(
                        job_type="http_probe",
                        target_ref=probe_url,
                        arguments=http_arguments,
                        timeout_seconds=timeout_seconds,
                        retry_limit=retry_limit,
                        summary=f"Enumerate {probe_url}.",
                    )
                )
            if include_tls and base_url.startswith("https://"):
                tls_target = self._derive_tls_target_from_url(base_url)
                if tls_target and tls_target not in seen_tls_targets:
                    seen_tls_targets.add(tls_target)
                    templates.append(
                        SkillWorkflowJobTemplate(
                            job_type="tls_inspect",
                            target_ref=tls_target,
                            arguments={},
                            timeout_seconds=timeout_seconds,
                            retry_limit=retry_limit,
                            summary=f"Inspect TLS for {tls_target}.",
                        )
                    )

        return _dedupe_templates(templates)

    def _parse_primary_target(self, primary_target: str) -> _WorkflowTarget:
        raw_target = primary_target.strip()
        request = AdmissionRequest(
            operation_id="workflow",
            job_id=None,
            tool_name="workflow",
            tool_category="recon",
            raw_target=raw_target,
        )
        descriptor = self.scope_validator.describe_target(request)
        if "://" in raw_target:
            parsed = urlsplit(raw_target)
            return _WorkflowTarget(
                raw_target=raw_target,
                host=descriptor.host or parsed.hostname or raw_target,
                is_url=True,
                is_ip_literal=_looks_like_ip_literal(parsed.hostname or descriptor.host or ""),
                scheme=parsed.scheme.lower(),
                port=parsed.port,
                base_url=_base_url(parsed),
            )
        return _WorkflowTarget(
            raw_target=raw_target,
            host=descriptor.host or raw_target,
            is_url=False,
            is_ip_literal=descriptor.kind == "ip",
            scheme=descriptor.protocol,
            port=descriptor.port,
        )

    def _derive_probe_urls(self, target: _WorkflowTarget) -> list[str]:
        if target.is_url and target.base_url is not None:
            return [target.base_url]
        if target.port is None:
            return [
                _build_url("http", target.host, None),
                _build_url("https", target.host, None),
            ]
        if target.port == 80:
            return [_build_url("http", target.host, target.port)]
        if target.port == 443:
            return [_build_url("https", target.host, target.port)]
        return [
            _build_url("http", target.host, target.port),
            _build_url("https", target.host, target.port),
        ]

    def _derive_tls_target(self, target: _WorkflowTarget) -> str | None:
        if target.is_url and target.scheme == "https":
            return self._derive_tls_target_from_url(target.base_url or target.raw_target)
        if target.port is not None and not target.is_url:
            return f"{target.host}:{target.port}"
        return f"{target.host}:443"

    def _derive_tls_target_from_url(self, value: str) -> str | None:
        parsed = urlsplit(value)
        if not parsed.hostname:
            return None
        port = parsed.port or 443
        return f"{parsed.hostname}:{port}"


def _base_url(parsed: SplitResult) -> str:
    return f"{parsed.scheme}://{parsed.netloc}"


def _looks_like_ip_literal(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _format_url_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _build_url(scheme: str, host: str, port: int | None) -> str:
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    netloc = _format_url_host(host)
    if port is not None and port != default_port:
        netloc = f"{netloc}:{port}"
    return f"{scheme}://{netloc}"


def _join_url_path(base_url: str, path: str) -> str:
    normalized_path = path.strip() or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if normalized_path == "/":
        return base_url
    return f"{base_url}{normalized_path}"


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1"}:
            return True
        if normalized in {"false", "no", "n", "0"}:
            return False
    raise ValueError("Boolean overrides must be true/false.")


def _coerce_optional_positive_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be an integer.") from exc
    if normalized <= 0:
        raise ValueError("timeout_seconds must be greater than 0.")
    return normalized


def _coerce_non_negative_int(value: object, *, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("retry_limit must be an integer.") from exc
    if normalized < 0:
        raise ValueError("retry_limit must be greater than or equal to 0.")
    return normalized


def _coerce_path_list(value: object, *, default: tuple[str, ...]) -> list[str]:
    if value in (None, ""):
        return list(default)
    if not isinstance(value, list):
        raise ValueError("paths must be a JSON list when provided.")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("paths entries must be non-empty strings.")
        normalized.append(item.strip())
    return normalized


def _dedupe_templates(templates: list[SkillWorkflowJobTemplate]) -> list[SkillWorkflowJobTemplate]:
    deduped: list[SkillWorkflowJobTemplate] = []
    seen: set[tuple[str, str, tuple[tuple[str, str], ...], int | None, int]] = set()
    for template in templates:
        signature = (
            template.job_type,
            template.target_ref,
            tuple(
                (key, repr(value))
                for key, value in sorted(template.arguments.items())
            ),
            template.timeout_seconds,
            template.retry_limit,
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(template)
    return deduped
