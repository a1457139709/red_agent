from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit
import json

from agent.provider import create_model
from agent.settings import Settings, get_settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.job_service import JobService
from app.memory_service import MemoryService
from app.operation_service import OperationService
from langchain_core.messages import HumanMessage, SystemMessage
from models.artifact import Artifact
from models.finding import Finding, FindingStatus
from models.job import Job, JobStatus
from models.memory import MemoryEntry
from models.operation import Operation
from models.planner import (
    OperationContextSummary,
    PlannerProposal,
    PlannerProposalApplyStatus,
    PlannerProposalKind,
    PlannerSource,
)
from models.scope_policy import ScopePolicy
from orchestration.scope_validator import AdmissionOutcome, ScopeValidator
from tools import build_security_tool_registry
from tools.executor import SecurityToolExecutionError, SecurityToolExecutor

ALLOWED_MEMORY_FAMILIES = {
    "service",
    "host",
    "web",
    "tls",
    "finding_summary",
    "workflow_rule",
    "operator_note",
}
DEFAULT_PLANNING_MODE = "next_steps"
MAX_PROPOSED_JOBS = 5
MIN_DESIRED_PROPOSALS = 3
MAX_CONTEXT_ITEMS = 5


@dataclass(frozen=True, slots=True)
class PlannerContext:
    operation: Operation
    policy: ScopePolicy
    successful_jobs: list[Job]
    evidence_items: list[Artifact]
    open_findings: list[Finding]
    memory_entries: list[MemoryEntry]
    context_hash: str

    @property
    def artifact_items(self) -> list[Artifact]:
        return self.evidence_items


@dataclass(frozen=True, slots=True)
class PlannerRuntimeCandidate:
    job_type: str
    target_ref: str
    arguments: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = None
    retry_limit: int = 0
    summary: str = ""
    rationale: str = ""
    forced_kind: PlannerProposalKind | None = None
    skip_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PlannerRuntimeResult:
    planning_mode: str
    summary: str
    rationale: str
    planner_source: PlannerSource
    model_name: str | None
    context: PlannerContext
    proposals: list[PlannerProposal]


@dataclass(frozen=True, slots=True)
class PlannerDerivedMemoryCandidate:
    entry_type: str
    key: str
    value: dict[str, Any]
    summary: str
    source_job_identifier: str | None = None


@dataclass(frozen=True, slots=True)
class PlannerDerivedMemoryResult:
    candidates: list[PlannerDerivedMemoryCandidate]
    skipped_count: int = 0


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part.strip()).strip()
    return str(content).strip()


def _extract_json_payload(text: str) -> str:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    return normalized


def _looks_like_url(value: str) -> bool:
    return "://" in value


def _normalize_host(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _host_from_target(value: str) -> str | None:
    target = value.strip()
    if not target:
        return None
    if _looks_like_url(target):
        parsed = urlsplit(target)
        return parsed.hostname.lower() if parsed.hostname else None
    if ":" in target:
        parsed = urlsplit(f"//{target}")
        return parsed.hostname.lower() if parsed.hostname else None
    return _normalize_host(target)


def _http_targets_from_host(host: str) -> list[str]:
    normalized = _normalize_host(host)
    return [f"https://{normalized}", f"http://{normalized}"]


def _tls_target_from_value(value: str) -> str | None:
    target = value.strip()
    if not target:
        return None
    if _looks_like_url(target):
        parsed = urlsplit(target)
        if not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 443)
        return f"{parsed.hostname.lower()}:{port}"
    if ":" in target:
        parsed = urlsplit(f"//{target}")
        if parsed.hostname and parsed.port:
            return f"{parsed.hostname.lower()}:{parsed.port}"
    host = _host_from_target(target)
    if host is None:
        return None
    return f"{host}:443"


def _normalize_value_signature(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _ordered_unique(items: Iterable[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


class PlannerRuntime:
    def __init__(
        self,
        *,
        operation_service: OperationService,
        job_service: JobService,
        finding_service: FindingService,
        memory_service: MemoryService,
        settings: Settings,
        artifact_service: ArtifactService | None = None,
        evidence_service: Any | None = None,
        security_tool_executor: SecurityToolExecutor | None = None,
        scope_validator: ScopeValidator | None = None,
        model_factory: Callable[[Settings], Any] | None = None,
    ) -> None:
        self.operation_service = operation_service
        self.job_service = job_service
        resolved_artifact_service = artifact_service
        if resolved_artifact_service is None and evidence_service is not None:
            resolved_artifact_service = getattr(evidence_service, "artifact_service", None)
        if resolved_artifact_service is None:
            resolved_artifact_service = ArtifactService.from_settings(settings)
        self.artifact_service = resolved_artifact_service
        if evidence_service is None:
            from app.evidence_service import EvidenceService

            evidence_service = EvidenceService(resolved_artifact_service, settings)
        self.evidence_service = evidence_service
        self.finding_service = finding_service
        self.memory_service = memory_service
        self.settings = settings
        self.security_tool_executor = security_tool_executor or SecurityToolExecutor(build_security_tool_registry())
        self.scope_validator = scope_validator or ScopeValidator()
        self.model_factory = model_factory or create_model

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "PlannerRuntime":
        settings = settings or get_settings()
        return cls(
            operation_service=OperationService.from_settings(settings),
            job_service=JobService.from_settings(settings),
            artifact_service=ArtifactService.from_settings(settings),
            finding_service=FindingService.from_settings(settings),
            memory_service=MemoryService.from_settings(settings),
            settings=settings,
        )

    def build_context(self, session_identifier: str) -> PlannerContext:
        operation = self.operation_service.require_operation(session_identifier)
        policy = self.operation_service.require_scope_policy(operation.id)
        jobs = self.job_service.list_jobs(operation.id, limit=50)
        artifact_items = self.artifact_service.list_artifacts(operation.id, limit=20)
        findings = self.finding_service.list_findings(operation.id, limit=20)
        memory_entries = self.memory_service.list_memory_entries(operation.id, limit=20)
        successful_jobs = [job for job in jobs if job.status == JobStatus.SUCCEEDED][:10]
        open_findings = [finding for finding in findings if finding.status == FindingStatus.OPEN][:10]

        context_payload = {
            "operation": {
                "id": operation.id,
                "public_id": operation.public_id,
                "objective": operation.objective,
                "status": operation.status.value,
            },
            "policy": {
                "allowed_hosts": policy.allowed_hosts,
                "allowed_domains": policy.allowed_domains,
                "allowed_ports": policy.allowed_ports,
                "allowed_protocols": policy.allowed_protocols,
                "allowed_tool_categories": policy.allowed_tool_categories,
                "denied_targets": policy.denied_targets,
            },
            "jobs": [
                {
                    "public_id": job.public_id,
                    "job_type": job.job_type,
                    "target_ref": job.target_ref,
                    "status": job.status.value,
                    "updated_at": job.updated_at,
                }
                for job in successful_jobs
            ],
            "artifacts": [
                {
                    "public_id": artifact.public_id,
                    "artifact_type": artifact.artifact_type,
                    "target_ref": artifact.target_ref,
                    "title": artifact.title,
                    "captured_at": artifact.captured_at,
                }
                for artifact in artifact_items
            ],
            "findings": [
                {
                    "public_id": finding.public_id,
                    "finding_type": finding.finding_type,
                    "title": finding.title,
                    "target_ref": finding.target_ref,
                    "severity": finding.severity,
                    "status": finding.status.value,
                }
                for finding in open_findings
            ],
            "memory": [
                {
                    "id": entry.id,
                    "entry_type": entry.entry_type,
                    "key": entry.key,
                    "summary": entry.summary,
                    "updated_at": entry.updated_at,
                }
                for entry in memory_entries
            ],
        }
        context_hash = sha256(
            json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return PlannerContext(
            operation=operation,
            policy=policy,
            successful_jobs=successful_jobs,
            evidence_items=artifact_items,
            open_findings=open_findings,
            memory_entries=memory_entries,
            context_hash=context_hash,
        )

    def create_plan(self, session_identifier: str) -> PlannerRuntimeResult:
        context = self.build_context(session_identifier)
        model_result = self._try_model_plan(context)
        if model_result is not None and any(
            proposal.proposal_kind == PlannerProposalKind.PROPOSED
            for proposal in model_result.proposals
        ):
            return model_result
        return self._build_fallback_plan(context)

    def derive_memory_candidates(self, session_identifier: str) -> PlannerDerivedMemoryResult:
        context = self.build_context(session_identifier)
        return self.derive_memory_candidates_from_context(context)

    def derive_memory_candidates_from_context(self, context: PlannerContext) -> PlannerDerivedMemoryResult:
        candidates: list[PlannerDerivedMemoryCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        skipped_count = 0

        def append_candidate(candidate: PlannerDerivedMemoryCandidate | None) -> None:
            nonlocal skipped_count
            if candidate is None:
                return
            signature = (
                candidate.entry_type,
                candidate.key,
                _normalize_value_signature(candidate.value),
            )
            if signature in seen:
                skipped_count += 1
                return
            seen.add(signature)
            candidates.append(candidate)

        for job in context.successful_jobs:
            append_candidate(self._candidate_from_job(job))
        for artifact in context.artifact_items:
            append_candidate(self._candidate_from_evidence(artifact))
        for finding in context.open_findings:
            append_candidate(self._candidate_from_finding(finding))
        return PlannerDerivedMemoryResult(candidates=candidates, skipped_count=skipped_count)

    def build_operation_context_summary(self, session_identifier: str) -> OperationContextSummary:
        context = self.build_context(session_identifier)
        fallback = self._build_fallback_plan(context)
        next_steps = [
            proposal.summary
            for proposal in fallback.proposals
            if proposal.proposal_kind == PlannerProposalKind.PROPOSED
        ][:2]
        return OperationContextSummary(
            session_id=context.operation.public_id or context.operation.id,
            summary=fallback.summary,
            scope_summary=self._build_scope_summary(context.policy),
            findings_summary=self._build_findings_summary(context.open_findings),
            evidence_summary=self._build_evidence_summary(context.artifact_items),
            memory_summary=self._build_memory_summary(context.memory_entries),
            next_step_hint=(
                "; ".join(next_steps)
                if next_steps
                else "Run /planner plan to generate next-step proposals."
            ),
        )

    def revalidate_proposal(
        self,
        *,
        operation: Operation,
        policy: ScopePolicy,
        proposal: PlannerProposal,
    ) -> tuple[bool, str | None]:
        candidate = PlannerRuntimeCandidate(
            job_type=proposal.job_type,
            target_ref=proposal.target_ref,
            arguments=dict(proposal.arguments),
            timeout_seconds=proposal.timeout_seconds,
            retry_limit=proposal.retry_limit,
            summary=proposal.summary,
            rationale=proposal.rationale,
        )
        validated = self._precheck_candidate(
            operation=operation,
            policy=policy,
            candidate=candidate,
        )
        if validated.proposal_kind != PlannerProposalKind.PROPOSED:
            return False, validated.skip_reason or "Proposal is no longer applicable."
        return True, validated.skip_reason

    def _try_model_plan(self, context: PlannerContext) -> PlannerRuntimeResult | None:
        try:
            model = self.model_factory(self.settings)
            response = model.invoke(
                [
                    SystemMessage(content=self._planner_system_prompt()),
                    HumanMessage(content=self._planner_user_prompt(context)),
                ]
            )
            content = _normalize_message_content(getattr(response, "content", response))
            parsed = json.loads(_extract_json_payload(content))
        except Exception:
            return None

        if not isinstance(parsed, dict):
            return None
        raw_proposals = parsed.get("proposals", [])
        if not isinstance(raw_proposals, list):
            return None

        candidates = self._normalize_model_candidates(raw_proposals)
        summary = str(parsed.get("summary", "")).strip()
        rationale = str(parsed.get("rationale", "")).strip()
        return self._finalize_result(
            context=context,
            planning_mode=DEFAULT_PLANNING_MODE,
            summary=summary or self._build_summary(context),
            rationale=rationale or self._build_rationale(context, candidates),
            planner_source=PlannerSource.MODEL,
            model_name=self.settings.openai_model,
            candidates=candidates,
        )

    def _build_fallback_plan(self, context: PlannerContext) -> PlannerRuntimeResult:
        candidates = self._build_fallback_candidates(context)
        return self._finalize_result(
            context=context,
            planning_mode=DEFAULT_PLANNING_MODE,
            summary=self._build_summary(context),
            rationale=self._build_rationale(context, candidates),
            planner_source=PlannerSource.FALLBACK,
            model_name=None,
            candidates=candidates,
        )

    def _finalize_result(
        self,
        *,
        context: PlannerContext,
        planning_mode: str,
        summary: str,
        rationale: str,
        planner_source: PlannerSource,
        model_name: str | None,
        candidates: Sequence[PlannerRuntimeCandidate],
    ) -> PlannerRuntimeResult:
        proposals: list[PlannerProposal] = []
        proposed_count = 0
        for candidate in candidates:
            proposal = self._precheck_candidate(
                operation=context.operation,
                policy=context.policy,
                candidate=candidate,
            )
            if proposal.proposal_kind == PlannerProposalKind.PROPOSED:
                if proposed_count >= MAX_PROPOSED_JOBS:
                    proposal.proposal_kind = PlannerProposalKind.SKIPPED
                    proposal.skip_reason = "Trimmed to the planner output limit."
                    proposal.proposal_index = 0
                else:
                    proposed_count += 1
                    proposal.proposal_index = proposed_count
            proposals.append(proposal)
        return PlannerRuntimeResult(
            planning_mode=planning_mode,
            summary=summary,
            rationale=rationale,
            planner_source=planner_source,
            model_name=model_name,
            context=context,
            proposals=proposals,
        )

    def _precheck_candidate(
        self,
        *,
        operation: Operation,
        policy: ScopePolicy,
        candidate: PlannerRuntimeCandidate,
    ) -> PlannerProposal:
        if candidate.forced_kind is not None:
            return PlannerProposal.create(
                plan_id="pending",
                proposal_index=0,
                proposal_kind=candidate.forced_kind,
                job_type=candidate.job_type or "unknown",
                target_ref=candidate.target_ref or "-",
                arguments=candidate.arguments,
                timeout_seconds=candidate.timeout_seconds,
                retry_limit=candidate.retry_limit,
                summary=candidate.summary,
                rationale=candidate.rationale,
                skip_reason=candidate.skip_reason,
            )
        try:
            tool = self.security_tool_executor.get_tool(candidate.job_type)
            invocation = self.security_tool_executor.validate(
                candidate.job_type,
                target=candidate.target_ref,
                arguments=self._effective_arguments(candidate),
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
            return PlannerProposal.create(
                plan_id="pending",
                proposal_index=0,
                proposal_kind=PlannerProposalKind.SKIPPED,
                job_type=candidate.job_type,
                target_ref=candidate.target_ref,
                arguments=candidate.arguments,
                timeout_seconds=candidate.timeout_seconds,
                retry_limit=candidate.retry_limit,
                summary=candidate.summary,
                rationale=candidate.rationale,
                skip_reason=exc.error,
            )

        if decision.outcome == AdmissionOutcome.DENIED:
            return PlannerProposal.create(
                plan_id="pending",
                proposal_index=0,
                proposal_kind=PlannerProposalKind.BLOCKED,
                job_type=candidate.job_type,
                target_ref=candidate.target_ref,
                arguments=candidate.arguments,
                timeout_seconds=candidate.timeout_seconds,
                retry_limit=candidate.retry_limit,
                summary=candidate.summary,
                rationale=candidate.rationale,
                skip_reason=decision.message,
            )

        effective_rationale = candidate.rationale.strip()
        if decision.outcome == AdmissionOutcome.REQUIRES_CONFIRMATION:
            note = "Requires operator confirmation during execution."
            effective_rationale = f"{effective_rationale} {note}".strip()

        return PlannerProposal.create(
            plan_id="pending",
            proposal_index=0,
            proposal_kind=PlannerProposalKind.PROPOSED,
            job_type=candidate.job_type,
            target_ref=candidate.target_ref,
            arguments=candidate.arguments,
            timeout_seconds=candidate.timeout_seconds,
            retry_limit=candidate.retry_limit,
            summary=candidate.summary,
            rationale=effective_rationale,
            apply_status=PlannerProposalApplyStatus.PENDING,
        )

    def _effective_arguments(self, candidate: PlannerRuntimeCandidate) -> dict[str, Any]:
        arguments = dict(candidate.arguments)
        if candidate.timeout_seconds is not None:
            arguments["timeout_seconds"] = candidate.timeout_seconds
        return arguments

    def _normalize_model_candidates(self, raw_proposals: Sequence[Any]) -> list[PlannerRuntimeCandidate]:
        normalized: list[PlannerRuntimeCandidate] = []
        seen: set[tuple[str, str, str, int | None, int]] = set()
        for raw in raw_proposals:
            if len(normalized) >= MAX_PROPOSED_JOBS + 3:
                break
            normalized.append(self._normalize_model_candidate(raw, seen=seen))
        return normalized

    def _normalize_model_candidate(
        self,
        raw: Any,
        *,
        seen: set[tuple[str, str, str, int | None, int]],
    ) -> PlannerRuntimeCandidate:
        if not isinstance(raw, Mapping):
            return PlannerRuntimeCandidate(
                job_type="unknown",
                target_ref="-",
                summary="Discard malformed planner proposal.",
                rationale="The planner returned a non-object proposal entry.",
                forced_kind=PlannerProposalKind.SKIPPED,
                skip_reason="Malformed planner proposal entry.",
            )

        job_type = str(raw.get("job_type", "")).strip()
        target_ref = str(raw.get("target_ref", "")).strip()
        arguments = raw.get("arguments", {})
        timeout_seconds = raw.get("timeout_seconds")
        retry_limit = raw.get("retry_limit", 0)
        summary = str(raw.get("summary", "")).strip() or f"Inspect {target_ref or 'target'} with {job_type or 'typed tool'}."
        rationale = str(raw.get("rationale", "")).strip() or "Derived from the current operation context."

        if not isinstance(arguments, Mapping):
            return PlannerRuntimeCandidate(
                job_type=job_type or "unknown",
                target_ref=target_ref or "-",
                summary=summary,
                rationale=rationale,
                forced_kind=PlannerProposalKind.SKIPPED,
                skip_reason="Planner proposal arguments must decode to an object.",
            )
        try:
            normalized_retry_limit = int(retry_limit)
        except (TypeError, ValueError):
            normalized_retry_limit = 0
        normalized_timeout = None
        if timeout_seconds not in (None, ""):
            try:
                normalized_timeout = int(timeout_seconds)
            except (TypeError, ValueError):
                return PlannerRuntimeCandidate(
                    job_type=job_type or "unknown",
                    target_ref=target_ref or "-",
                    arguments=dict(arguments),
                    summary=summary,
                    rationale=rationale,
                    forced_kind=PlannerProposalKind.SKIPPED,
                    skip_reason="Planner proposal timeout_seconds must be an integer.",
                )
        if not job_type or not target_ref:
            return PlannerRuntimeCandidate(
                job_type=job_type or "unknown",
                target_ref=target_ref or "-",
                arguments=dict(arguments),
                summary=summary,
                rationale=rationale,
                forced_kind=PlannerProposalKind.SKIPPED,
                skip_reason="Planner proposal must include job_type and target_ref.",
            )
        signature = (
            job_type,
            target_ref,
            json.dumps(dict(arguments), ensure_ascii=False, sort_keys=True),
            normalized_timeout,
            normalized_retry_limit,
        )
        if signature in seen:
            return PlannerRuntimeCandidate(
                job_type=job_type,
                target_ref=target_ref,
                arguments=dict(arguments),
                timeout_seconds=normalized_timeout,
                retry_limit=normalized_retry_limit,
                summary=summary,
                rationale=rationale,
                forced_kind=PlannerProposalKind.SKIPPED,
                skip_reason="Duplicate proposal removed during normalization.",
            )
        seen.add(signature)
        return PlannerRuntimeCandidate(
            job_type=job_type,
            target_ref=target_ref,
            arguments=dict(arguments),
            timeout_seconds=normalized_timeout,
            retry_limit=max(0, normalized_retry_limit),
            summary=summary,
            rationale=rationale,
        )

    def _build_fallback_candidates(self, context: PlannerContext) -> list[PlannerRuntimeCandidate]:
        candidates: list[PlannerRuntimeCandidate] = []
        seen: set[tuple[str, str, str, int | None, int]] = set()

        def append_candidate(candidate: PlannerRuntimeCandidate) -> None:
            signature = (
                candidate.job_type,
                candidate.target_ref,
                json.dumps(candidate.arguments, ensure_ascii=False, sort_keys=True),
                candidate.timeout_seconds,
                candidate.retry_limit,
            )
            if signature in seen:
                continue_flag = True
            else:
                continue_flag = False
                seen.add(signature)
            if continue_flag:
                return
            candidates.append(candidate)

        for finding in context.open_findings:
            if finding.finding_type.startswith("tls_"):
                tls_target = _tls_target_from_value(finding.target_ref)
                if tls_target is not None:
                    append_candidate(
                        PlannerRuntimeCandidate(
                            job_type="tls_inspect",
                            target_ref=tls_target,
                            summary=f"Re-check TLS state for {tls_target}.",
                            rationale=f"Open finding '{finding.title}' suggests TLS verification is still warranted.",
                        )
                    )
            if _looks_like_url(finding.target_ref):
                append_candidate(
                    PlannerRuntimeCandidate(
                        job_type="http_probe",
                        target_ref=finding.target_ref,
                        arguments={"method": "GET"},
                        summary=f"Re-probe {finding.target_ref}.",
                        rationale=f"Open finding '{finding.title}' should be validated against the live endpoint.",
                    )
                )
            else:
                host = _host_from_target(finding.target_ref)
                if host is not None:
                    append_candidate(
                        PlannerRuntimeCandidate(
                            job_type="dns_lookup",
                            target_ref=host,
                            arguments={"record_type": "A"},
                            summary=f"Refresh DNS resolution for {host}.",
                            rationale=f"Open finding '{finding.title}' references {host} and may depend on current DNS data.",
                        )
                    )

        for artifact in context.artifact_items[:MAX_CONTEXT_ITEMS]:
            if artifact.evidence_type == "http_response" and _looks_like_url(artifact.target_ref):
                append_candidate(
                    PlannerRuntimeCandidate(
                        job_type="http_probe",
                        target_ref=artifact.target_ref,
                        arguments={"method": "GET"},
                        summary=f"Refresh HTTP artifact coverage for {artifact.target_ref}.",
                        rationale=f"Recent artifact '{artifact.title}' indicates this web target remains relevant.",
                    )
                )
                tls_target = _tls_target_from_value(artifact.target_ref)
                if artifact.target_ref.startswith("https://") and tls_target is not None:
                    append_candidate(
                        PlannerRuntimeCandidate(
                            job_type="tls_inspect",
                            target_ref=tls_target,
                            summary=f"Refresh TLS artifact coverage for {tls_target}.",
                            rationale=f"Recent HTTPS artifact '{artifact.title}' should be paired with current certificate details.",
                        )
                    )
            elif artifact.evidence_type == "tls_certificate":
                tls_target = _tls_target_from_value(artifact.target_ref)
                if tls_target is not None:
                    append_candidate(
                        PlannerRuntimeCandidate(
                            job_type="tls_inspect",
                            target_ref=tls_target,
                            summary=f"Verify TLS details for {tls_target}.",
                            rationale=f"Recent certificate artifact '{artifact.title}' should be checked for drift.",
                        )
                    )

        for entry in context.memory_entries[:MAX_CONTEXT_ITEMS]:
            family = self._memory_family(entry)
            host = self._host_from_memory_entry(entry)
            if family in {"service", "host", "workflow_rule"} and host is not None:
                append_candidate(
                    PlannerRuntimeCandidate(
                        job_type="dns_lookup",
                        target_ref=host,
                        arguments={"record_type": "A"},
                        summary=f"Resolve {host}.",
                        rationale=f"Structured memory notes {host} as a stable target worth refreshing.",
                    )
                )
            if family in {"web", "service"} and host is not None:
                for url in _http_targets_from_host(host):
                    append_candidate(
                        PlannerRuntimeCandidate(
                            job_type="http_probe",
                            target_ref=url,
                            arguments={"method": "GET"},
                            summary=f"Probe {url}.",
                            rationale=f"Structured memory marks {host} as a web-relevant target.",
                        )
                    )
                if family == "service":
                    append_candidate(
                        PlannerRuntimeCandidate(
                            job_type="tls_inspect",
                            target_ref=f"{host}:443",
                            summary=f"Inspect TLS for {host}:443.",
                            rationale=f"Structured memory marks {host} as an externally reachable service.",
                        )
                    )
            if family == "tls" and host is not None:
                append_candidate(
                    PlannerRuntimeCandidate(
                        job_type="tls_inspect",
                        target_ref=f"{host}:443",
                        summary=f"Inspect TLS for {host}:443.",
                        rationale=f"Structured memory marks {host} as TLS-relevant.",
                    )
                )

        for host in _ordered_unique([*context.policy.allowed_hosts, *context.policy.allowed_domains])[:MAX_CONTEXT_ITEMS]:
            append_candidate(
                PlannerRuntimeCandidate(
                    job_type="dns_lookup",
                    target_ref=host,
                    arguments={"record_type": "A"},
                    summary=f"Resolve {host}.",
                    rationale="This target is explicitly in scope and is a safe starting point for refreshed reconnaissance.",
                )
            )
            for url in _http_targets_from_host(host):
                append_candidate(
                    PlannerRuntimeCandidate(
                        job_type="http_probe",
                        target_ref=url,
                        arguments={"method": "GET"},
                        summary=f"Probe {url}.",
                        rationale="This target is explicitly in scope and suitable for lightweight HTTP verification.",
                    )
                )
            append_candidate(
                PlannerRuntimeCandidate(
                    job_type="tls_inspect",
                    target_ref=f"{host}:443",
                    summary=f"Inspect TLS for {host}:443.",
                    rationale="This in-scope host may expose HTTPS services that benefit from certificate inspection.",
                )
            )

        if not candidates:
            candidates.append(
                PlannerRuntimeCandidate(
                    job_type="unknown",
                    target_ref="-",
                    summary="No obvious scoped targets were derived from operation state.",
                    rationale="Fallback planner could not derive a reliable in-scope target from current facts.",
                    forced_kind=PlannerProposalKind.SKIPPED,
                    skip_reason="No viable in-scope planner candidates were derived from current operation facts.",
                )
            )
        return candidates

    def _build_summary(self, context: PlannerContext) -> str:
        return " ".join(
            part
            for part in [
                f"Operation objective: {context.operation.objective}.",
                self._build_scope_summary(context.policy),
                self._build_findings_summary(context.open_findings),
            self._build_evidence_summary(context.artifact_items),
                self._build_memory_summary(context.memory_entries),
            ]
            if part
        ).strip()

    def _build_rationale(
        self,
        context: PlannerContext,
        candidates: Sequence[PlannerRuntimeCandidate],
    ) -> str:
        reasons: list[str] = []
        if context.open_findings:
            reasons.append("Open findings are prioritized so unresolved risk can be revalidated.")
        if context.artifact_items:
            reasons.append("Recent artifacts are reused to avoid replaying transcript history.")
        if any(self._memory_family(entry) in ALLOWED_MEMORY_FAMILIES for entry in context.memory_entries):
            reasons.append("Structured memory contributes stable target facts and workflow hints.")
        if not reasons:
            reasons.append("The planner falls back to declared scope seeds when few persisted facts are available.")
        if candidates:
            reasons.append(
                f"Generated up to {min(len(candidates), MAX_PROPOSED_JOBS)} next-step candidates using typed security tools only."
            )
        return " ".join(reasons)

    def _build_scope_summary(self, policy: ScopePolicy) -> str:
        targets = _ordered_unique([*policy.allowed_hosts, *policy.allowed_domains])
        target_label = ", ".join(targets[:3]) or "no explicit host/domain seeds"
        ports = ", ".join(str(port) for port in policy.allowed_ports[:5]) or "any declared port"
        protocols = ", ".join(policy.allowed_protocols[:5]) or "any declared protocol"
        return f"Scope allows {target_label}; ports {ports}; protocols {protocols}."

    def _build_findings_summary(self, findings: Sequence[Finding]) -> str:
        if not findings:
            return "No open findings are currently recorded."
        highlights = ", ".join(
            _truncate_text(f"{finding.title} ({finding.severity})", limit=80)
            for finding in findings[:3]
        )
        return f"{len(findings)} open finding(s): {highlights}."

    def _build_evidence_summary(self, evidence_items: Sequence[Artifact]) -> str:
        if not evidence_items:
            return "No recent artifacts are stored yet."
        highlights = ", ".join(
            _truncate_text(f"{item.title} on {item.target_ref}", limit=80)
            for item in evidence_items[:3]
        )
        return f"{len(evidence_items)} recent artifact item(s): {highlights}."

    def _build_memory_summary(self, memory_entries: Sequence[MemoryEntry]) -> str:
        if not memory_entries:
            return "No structured memory facts are stored yet."
        highlights = ", ".join(
            _truncate_text(entry.summary, limit=80)
            for entry in memory_entries[:3]
        )
        return f"{len(memory_entries)} memory fact(s): {highlights}."

    def _memory_family(self, entry: MemoryEntry) -> str:
        normalized_type = entry.entry_type.strip().lower()
        if normalized_type in ALLOWED_MEMORY_FAMILIES:
            return normalized_type
        normalized_key = entry.key.strip().lower()
        if normalized_key in ALLOWED_MEMORY_FAMILIES:
            return normalized_key
        return "note"

    def _host_from_memory_entry(self, entry: MemoryEntry) -> str | None:
        candidates: list[str] = []
        if isinstance(entry.value, dict):
            for key in ("host", "hostname", "domain", "target", "url"):
                value = entry.value.get(key)
                if isinstance(value, str):
                    candidates.append(value)
        elif isinstance(entry.value, list):
            for value in entry.value:
                if isinstance(value, str):
                    candidates.append(value)
        elif isinstance(entry.value, str):
            candidates.append(entry.value)
        candidates.extend([entry.key, entry.summary])
        for value in candidates:
            host = _host_from_target(str(value))
            if host:
                return host
        return None

    def _candidate_from_job(self, job: Job) -> PlannerDerivedMemoryCandidate | None:
        source_type_map = {
            "dns_lookup": "host",
            "http_probe": "web",
            "tls_inspect": "tls",
            "port_scan": "host",
            "banner_grab": "host",
        }
        source_type = source_type_map.get(job.job_type)
        if source_type is None:
            return None
        return self._build_memory_candidate(
            source_type=source_type,
            origin_kind="job",
            origin_ref=job.public_id or job.id,
            target_ref=job.target_ref,
            source_job_identifier=job.id,
        )

    def _candidate_from_evidence(self, evidence: Artifact) -> PlannerDerivedMemoryCandidate | None:
        source_type_map = {
            "dns_response": "host",
            "http_response": "web",
            "tls_certificate": "tls",
            "port_scan": "host",
            "banner": "host",
        }
        source_type = source_type_map.get(evidence.evidence_type)
        if source_type is None:
            return None
        return self._build_memory_candidate(
            source_type=source_type,
            origin_kind="artifact",
            origin_ref=evidence.public_id or evidence.id,
            target_ref=evidence.target_ref,
            source_job_identifier=evidence.job_id,
        )

    def _candidate_from_finding(self, finding: Finding) -> PlannerDerivedMemoryCandidate | None:
        source_type: str | None
        if finding.finding_type.startswith("tls_") or self._is_tls_target(finding.target_ref):
            source_type = "tls"
        elif _looks_like_url(finding.target_ref):
            source_type = "web"
        else:
            host = _host_from_target(finding.target_ref)
            source_type = "host" if host is not None else None
        if source_type is None:
            return None
        return self._build_memory_candidate(
            source_type=source_type,
            origin_kind="finding",
            origin_ref=finding.public_id or finding.id,
            target_ref=finding.target_ref,
            source_job_identifier=finding.source_job_id,
        )

    def _build_memory_candidate(
        self,
        *,
        source_type: str,
        origin_kind: str,
        origin_ref: str,
        target_ref: str,
        source_job_identifier: str | None,
    ) -> PlannerDerivedMemoryCandidate | None:
        if source_type == "host":
            host = _host_from_target(target_ref)
            if host is None:
                return None
            return PlannerDerivedMemoryCandidate(
                entry_type="host",
                key=host,
                value={
                    "host": host,
                    "target": target_ref,
                    "origin_kind": origin_kind,
                    "origin_ref": origin_ref,
                    "source_type": source_type,
                },
                summary=f"Planner recorded {host} as a stable host target.",
                source_job_identifier=source_job_identifier,
            )
        if source_type == "web":
            host = _host_from_target(target_ref)
            if host is None:
                return None
            url = target_ref if _looks_like_url(target_ref) else f"https://{host}"
            return PlannerDerivedMemoryCandidate(
                entry_type="web",
                key=host,
                value={
                    "host": host,
                    "url": url,
                    "origin_kind": origin_kind,
                    "origin_ref": origin_ref,
                    "source_type": source_type,
                },
                summary=f"Planner recorded {host} as a stable web target.",
                source_job_identifier=source_job_identifier,
            )
        if source_type == "tls":
            tls_target = _tls_target_from_value(target_ref)
            if tls_target is None:
                return None
            host = _host_from_target(tls_target)
            if host is None:
                return None
            return PlannerDerivedMemoryCandidate(
                entry_type="tls",
                key=tls_target,
                value={
                    "host": host,
                    "target": tls_target,
                    "origin_kind": origin_kind,
                    "origin_ref": origin_ref,
                    "source_type": source_type,
                },
                summary=f"Planner recorded {host} as a stable TLS-relevant target.",
                source_job_identifier=source_job_identifier,
            )
        return None

    def _is_tls_target(self, target_ref: str) -> bool:
        target = target_ref.strip().lower()
        return target.startswith("https://") or target.endswith(":443")

    def _planner_system_prompt(self) -> str:
        tool_names = ", ".join(sorted(self.security_tool_executor.tool_names))
        return (
            "You are a planner for a scoped security operation. "
            "Return JSON only. Do not suggest shell commands, freeform actions, or out-of-scope targets. "
            "Only propose typed security jobs using these job types: "
            f"{tool_names}. "
            "Return an object with keys: summary, rationale, proposals. "
            "Each proposal must include job_type, target_ref, arguments, summary, rationale, "
            "and may include timeout_seconds and retry_limit."
        )

    def _planner_user_prompt(self, context: PlannerContext) -> str:
        payload = {
            "operation": {
                "id": context.operation.public_id or context.operation.id,
                "title": context.operation.title,
                "objective": context.operation.objective,
                "status": context.operation.status.value,
            },
            "scope_policy": {
                "allowed_hosts": context.policy.allowed_hosts,
                "allowed_domains": context.policy.allowed_domains,
                "allowed_ports": context.policy.allowed_ports,
                "allowed_protocols": context.policy.allowed_protocols,
                "denied_targets": context.policy.denied_targets,
                "allowed_tool_categories": context.policy.allowed_tool_categories,
            },
            "recent_successful_jobs": [
                {
                    "job_type": job.job_type,
                    "target_ref": job.target_ref,
                    "arguments": job.arguments,
                }
                for job in context.successful_jobs[:MAX_CONTEXT_ITEMS]
            ],
            "recent_artifacts": [
                {
                    "artifact_type": artifact.evidence_type,
                    "target_ref": artifact.target_ref,
                    "title": artifact.title,
                    "summary": artifact.summary,
                }
                for artifact in context.artifact_items[:MAX_CONTEXT_ITEMS]
            ],
            "open_findings": [
                {
                    "finding_type": finding.finding_type,
                    "title": finding.title,
                    "target_ref": finding.target_ref,
                    "severity": finding.severity,
                    "summary": finding.summary,
                    "next_action": finding.next_action,
                }
                for finding in context.open_findings[:MAX_CONTEXT_ITEMS]
            ],
            "memory": [
                {
                    "family": self._memory_family(entry),
                    "key": entry.key,
                    "summary": entry.summary,
                    "value": entry.value,
                }
                for entry in context.memory_entries[:MAX_CONTEXT_ITEMS]
            ],
            "constraints": {
                "desired_proposal_count": MAX_PROPOSED_JOBS,
                "minimum_useful_count": MIN_DESIRED_PROPOSALS,
                "typed_tools_only": True,
                "do_not_expand_scope": True,
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
