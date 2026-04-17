from __future__ import annotations

from models.artifact import Artifact
from models.finding import Finding
from models.finding_artifact_link import FindingArtifactLink
from models.job import Job
from models.operation import Operation
from models.scope_policy import ScopePolicy
from models.session import Session


def build_operation_summary(
    *,
    session: Session,
    operation: Operation,
    policy: ScopePolicy,
    jobs: list[Job],
    artifacts: list[Artifact],
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
            "artifacts": len(artifacts),
            "evidence": len(artifacts),
            "findings": len(findings),
        },
        "session": {
            "id": session.id,
            "public_id": session.public_id,
            "title": session.title,
            "goal": session.goal,
            "mode": session.mode.value,
            "status": session.status.value,
            "target_summary": session.target_summary,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "closed_at": session.closed_at,
        },
        "job_status_counts": job_status_counts,
        "finding_status_counts": finding_status_counts,
    }


def build_findings_export(
    *,
    findings: list[Finding],
    links: list[FindingArtifactLink],
    artifacts_by_id: dict[str, Artifact],
) -> list[dict]:
    artifact_ids_by_finding: dict[str, list[str]] = {}
    for link in links:
        artifact = artifacts_by_id.get(link.artifact_id)
        if artifact is None:
            continue
        artifact_ids_by_finding.setdefault(link.finding_id, []).append(artifact.public_id)

    return [
        {
            "id": finding.id,
            "public_id": finding.public_id,
            "session_id": finding.session_id,
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
            "artifact_public_ids": artifact_ids_by_finding.get(finding.id, []),
            "evidence_public_ids": artifact_ids_by_finding.get(finding.id, []),
        }
        for finding in findings
    ]


def build_artifact_index_export(
    *,
    artifacts: list[Artifact],
    links: list[FindingArtifactLink],
    findings_by_id: dict[str, Finding],
) -> list[dict]:
    finding_ids_by_artifact: dict[str, list[str]] = {}
    for link in links:
        finding = findings_by_id.get(link.finding_id)
        if finding is None:
            continue
        finding_ids_by_artifact.setdefault(link.artifact_id, []).append(finding.public_id)

    return [
        {
            "id": item.id,
            "public_id": item.public_id,
            "session_id": item.session_id,
            "operation_id": item.operation_id,
            "source_job_id": item.source_job_id,
            "job_id": item.job_id,
            "artifact_type": item.artifact_type,
            "evidence_type": item.evidence_type,
            "target_ref": item.target_ref,
            "title": item.title,
            "summary": item.summary,
            "artifact_path": item.artifact_path,
            "content_type": item.content_type,
            "hash_digest": item.hash_digest,
            "captured_at": item.captured_at,
            "finding_public_ids": finding_ids_by_artifact.get(item.id, []),
        }
        for item in artifacts
    ]


def build_evidence_index_export(
    *,
    evidence: list[Artifact],
    links: list[FindingArtifactLink],
    findings_by_id: dict[str, Finding],
) -> list[dict]:
    return build_artifact_index_export(
        artifacts=evidence,
        links=links,
        findings_by_id=findings_by_id,
    )
