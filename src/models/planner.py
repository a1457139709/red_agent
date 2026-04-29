from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4
import json

from .run import utc_now_iso


class PlannerPlanStatus(StrEnum):
    PROPOSED = "proposed"
    PARTIALLY_APPLIED = "partially_applied"
    APPLIED = "applied"


class PlannerSource(StrEnum):
    MODEL = "model"
    FALLBACK = "fallback"


class PlannerProposalKind(StrEnum):
    PROPOSED = "proposed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class PlannerProposalApplyStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    SKIPPED = "skipped"


class PlannerMemoryWritebackStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class PlannerPlan:
    id: str
    public_id: str
    session_id: str
    status: PlannerPlanStatus
    planning_mode: str
    context_hash: str
    summary: str
    rationale: str
    planner_source: PlannerSource
    model_name: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    applied_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        planning_mode: str,
        context_hash: str,
        summary: str,
        rationale: str,
        planner_source: PlannerSource,
        model_name: str | None = None,
        status: PlannerPlanStatus = PlannerPlanStatus.PROPOSED,
    ) -> "PlannerPlan":
        return cls(
            id=str(uuid4()),
            public_id="",
            session_id=session_id,
            status=status,
            planning_mode=planning_mode,
            context_hash=context_hash,
            summary=summary,
            rationale=rationale,
            planner_source=planner_source,
            model_name=model_name,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlannerPlan":
        return cls(
            id=row["id"],
            public_id=row.get("public_id") or "",
            session_id=row["session_id"],
            status=PlannerPlanStatus(row["status"]),
            planning_mode=row["planning_mode"],
            context_hash=row["context_hash"],
            summary=row["summary"],
            rationale=row["rationale"],
            planner_source=PlannerSource(row["planner_source"]),
            model_name=row["model_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            applied_at=row["applied_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "planning_mode": self.planning_mode,
            "context_hash": self.context_hash,
            "summary": self.summary,
            "rationale": self.rationale,
            "planner_source": self.planner_source.value,
            "model_name": self.model_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "applied_at": self.applied_at,
        }

@dataclass(slots=True)
class PlannerProposal:
    id: str
    plan_id: str
    proposal_index: int
    proposal_kind: PlannerProposalKind
    apply_status: PlannerProposalApplyStatus
    job_type: str
    target_ref: str
    arguments: dict[str, Any]
    timeout_seconds: int | None = None
    retry_limit: int = 0
    summary: str = ""
    rationale: str = ""
    skip_reason: str | None = None
    created_job_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        proposal_index: int,
        proposal_kind: PlannerProposalKind,
        job_type: str,
        target_ref: str,
        arguments: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        retry_limit: int = 0,
        summary: str = "",
        rationale: str = "",
        skip_reason: str | None = None,
        apply_status: PlannerProposalApplyStatus = PlannerProposalApplyStatus.PENDING,
    ) -> "PlannerProposal":
        return cls(
            id=str(uuid4()),
            plan_id=plan_id,
            proposal_index=proposal_index,
            proposal_kind=proposal_kind,
            apply_status=apply_status,
            job_type=job_type,
            target_ref=target_ref,
            arguments=dict(arguments or {}),
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
            summary=summary,
            rationale=rationale,
            skip_reason=skip_reason,
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlannerProposal":
        return cls(
            id=row["id"],
            plan_id=row["plan_id"],
            proposal_index=row["proposal_index"],
            proposal_kind=PlannerProposalKind(row["proposal_kind"]),
            apply_status=PlannerProposalApplyStatus(row["apply_status"]),
            job_type=row["job_type"],
            target_ref=row["target_ref"],
            arguments=json.loads(row["arguments"]) if row.get("arguments") else {},
            timeout_seconds=row["timeout_seconds"],
            retry_limit=row["retry_limit"],
            summary=row["summary"],
            rationale=row["rationale"],
            skip_reason=row["skip_reason"],
            created_job_id=row["created_job_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "proposal_index": self.proposal_index,
            "proposal_kind": self.proposal_kind.value,
            "apply_status": self.apply_status.value,
            "job_type": self.job_type,
            "target_ref": self.target_ref,
            "arguments": json.dumps(self.arguments, ensure_ascii=False),
            "timeout_seconds": self.timeout_seconds,
            "retry_limit": self.retry_limit,
            "summary": self.summary,
            "rationale": self.rationale,
            "skip_reason": self.skip_reason,
            "created_job_id": self.created_job_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class SessionContextSummary:
    session_id: str
    summary: str
    scope_summary: str
    findings_summary: str
    artifact_summary: str
    memory_summary: str
    next_step_hint: str


@dataclass(frozen=True, slots=True)
class PlannerMemoryWritebackSummary:
    status: PlannerMemoryWritebackStatus
    created_count: int
    skipped_count: int
    error_message: str | None = None
