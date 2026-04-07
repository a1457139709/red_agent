from __future__ import annotations

from models.evidence import Evidence
from models.finding import Finding
from models.finding_evidence_link import FindingEvidenceLink
from models.job import Job
from models.operation import Operation
from models.scope_policy import ScopePolicy


def build_operation_summary(
    *,
    operation: Operation,
    policy: ScopePolicy,
    jobs: list[Job],
    evidence: list[Evidence],
    findings: list[Finding],
) -> dict:
    job_status_counts: dict[str, int] = {}
    finding_status_counts: dict[str, int] = {}

    for job in jobs:
        job_status_counts[job.status.value] = job_status_counts.get(job.status.value, 0) + 1
    for finding in findings:
        finding_status_counts[finding.status.value] = finding_status_counts.get(finding.status.value, 0) + 1

    return {
        "operation": {
            "id": operation.id,
            "public_id": operation.public_id,
            "title": operation.title,
            "objective": operation.objective,
            "workspace": operation.workspace,
            "status": operation.status.value,
            "created_at": operation.created_at,
            "updated_at": operation.updated_at,
            "closed_at": operation.closed_at,
            "last_error": operation.last_error,
        },
        "scope_policy": {
            "allowed_hosts": policy.allowed_hosts,
            "allowed_domains": policy.allowed_domains,
            "allowed_cidrs": policy.allowed_cidrs,
            "allowed_ports": policy.allowed_ports,
            "allowed_protocols": policy.allowed_protocols,
            "denied_targets": policy.denied_targets,
            "allowed_tool_categories": policy.allowed_tool_categories,
            "max_concurrency": policy.max_concurrency,
            "rate_limit_per_minute": policy.rate_limit_per_minute,
            "confirmation_required_actions": policy.confirmation_required_actions,
        },
        "counts": {
            "jobs": len(jobs),
            "evidence": len(evidence),
            "findings": len(findings),
        },
        "job_status_counts": job_status_counts,
        "finding_status_counts": finding_status_counts,
    }


def build_findings_export(
    *,
    findings: list[Finding],
    links: list[FindingEvidenceLink],
    evidence_by_id: dict[str, Evidence],
) -> list[dict]:
    evidence_ids_by_finding: dict[str, list[str]] = {}
    for link in links:
        evidence = evidence_by_id.get(link.evidence_id)
        if evidence is None:
            continue
        evidence_ids_by_finding.setdefault(link.finding_id, []).append(evidence.public_id)

    return [
        {
            "id": finding.id,
            "public_id": finding.public_id,
            "operation_id": finding.operation_id,
            "source_job_id": finding.source_job_id,
            "finding_type": finding.finding_type,
            "title": finding.title,
            "target_ref": finding.target_ref,
            "severity": finding.severity,
            "confidence": finding.confidence,
            "status": finding.status.value,
            "summary": finding.summary,
            "impact": finding.impact,
            "reproduction_notes": finding.reproduction_notes,
            "next_action": finding.next_action,
            "created_at": finding.created_at,
            "updated_at": finding.updated_at,
            "evidence_public_ids": evidence_ids_by_finding.get(finding.id, []),
        }
        for finding in findings
    ]


def build_evidence_index_export(
    *,
    evidence: list[Evidence],
    links: list[FindingEvidenceLink],
    findings_by_id: dict[str, Finding],
) -> list[dict]:
    finding_ids_by_evidence: dict[str, list[str]] = {}
    for link in links:
        finding = findings_by_id.get(link.finding_id)
        if finding is None:
            continue
        finding_ids_by_evidence.setdefault(link.evidence_id, []).append(finding.public_id)

    return [
        {
            "id": item.id,
            "public_id": item.public_id,
            "operation_id": item.operation_id,
            "job_id": item.job_id,
            "evidence_type": item.evidence_type,
            "target_ref": item.target_ref,
            "title": item.title,
            "summary": item.summary,
            "artifact_path": item.artifact_path,
            "content_type": item.content_type,
            "hash_digest": item.hash_digest,
            "captured_at": item.captured_at,
            "finding_public_ids": finding_ids_by_evidence.get(item.id, []),
        }
        for item in evidence
    ]
