from __future__ import annotations

from dataclasses import dataclass

from agent.settings import Settings, get_settings
from app.job_service import JobService
from app.memory_service import MemoryService
from app.operation_service import OperationService
from app.session_service import SessionService
from models.job import Job
from models.planner import (
    PlannerMemoryWritebackStatus,
    PlannerMemoryWritebackSummary,
    PlannerPlan,
    PlannerPlanStatus,
    PlannerProposal,
    PlannerProposalApplyStatus,
)
from models.run import utc_now_iso
from orchestration.planner_runtime import PlannerDerivedMemoryCandidate, PlannerRuntime
from storage.repositories.planner import PlannerRepository
from storage.sqlite import SQLiteStorage


@dataclass(frozen=True, slots=True)
class PlannerPlanBundle:
    plan: PlannerPlan
    proposals: list[PlannerProposal]
    memory_writeback: PlannerMemoryWritebackSummary | None = None


@dataclass(frozen=True, slots=True)
class PlannerApplyResult:
    plan: PlannerPlan
    proposals: list[PlannerProposal]
    applied_jobs: list[Job]
    skipped_proposals: list[PlannerProposal]


class PlannerService:
    def __init__(
        self,
        repository: PlannerRepository,
        runtime: PlannerRuntime,
        operation_service: OperationService,
        job_service: JobService,
        memory_service: MemoryService,
        settings: Settings,
        session_service: SessionService | None = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.operation_service = operation_service
        self.session_service = session_service or SessionService.from_settings(settings)
        self.job_service = job_service
        self.memory_service = memory_service
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "PlannerService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        operation_service = OperationService.from_settings(settings)
        job_service = JobService.from_settings(settings)
        return cls(
            repository=PlannerRepository(storage),
            runtime=PlannerRuntime.from_settings(settings),
            operation_service=operation_service,
            session_service=SessionService.from_settings(settings),
            job_service=job_service,
            memory_service=MemoryService.from_settings(settings),
            settings=settings,
        )

    def create_plan(self, session_identifier: str) -> PlannerPlanBundle:
        result = self.runtime.create_plan(session_identifier)
        plan = PlannerPlan.create(
            session_id=result.context.operation.id,
            planning_mode=result.planning_mode,
            context_hash=result.context.context_hash,
            summary=result.summary,
            rationale=result.rationale,
            planner_source=result.planner_source,
            model_name=result.model_name,
            status=PlannerPlanStatus.PROPOSED,
        )
        proposals: list[PlannerProposal] = []
        for proposal in result.proposals:
            proposal.plan_id = plan.id
            proposals.append(proposal)
        self.repository.create_plan(plan, proposals)
        memory_writeback = self._write_back_memory_candidates(result.context.operation.id)
        return PlannerPlanBundle(plan=plan, proposals=proposals, memory_writeback=memory_writeback)

    def get_plan_bundle(self, identifier: str) -> PlannerPlanBundle:
        plan = self.repository.get_plan(identifier)
        if plan is None:
            raise ValueError(f"Planner plan not found: {identifier}")
        return PlannerPlanBundle(plan=plan, proposals=self.repository.list_plan_proposals(plan.id))

    def apply_plan(
        self,
        identifier: str,
        *,
        selected_indices: list[int] | None = None,
    ) -> PlannerApplyResult:
        bundle = self.get_plan_bundle(identifier)
        operation = self.operation_service.require_operation(bundle.plan.session_id)
        policy = self.operation_service.require_scope_policy(operation.id)
        selectable = [
            proposal
            for proposal in bundle.proposals
            if proposal.proposal_kind.value == "proposed"
        ]
        selection = self._resolve_selection(selectable, selected_indices)
        applied_jobs: list[Job] = []
        skipped_proposals: list[PlannerProposal] = []
        state_changed = False

        for proposal in selection:
            if proposal.apply_status == PlannerProposalApplyStatus.APPLIED:
                skipped_proposals.append(proposal)
                continue
            is_valid, reason = self.runtime.revalidate_proposal(
                operation=operation,
                policy=policy,
                proposal=proposal,
            )
            if not is_valid:
                proposal.apply_status = PlannerProposalApplyStatus.SKIPPED
                proposal.skip_reason = reason or proposal.skip_reason
                proposal.updated_at = utc_now_iso()
                self.repository.update_proposal(proposal)
                state_changed = True
                skipped_proposals.append(proposal)
                continue

            job = self.job_service.create_job(
                session_identifier=bundle.plan.session_id,
                job_type=proposal.job_type,
                target_ref=proposal.target_ref,
                arguments=dict(proposal.arguments),
                timeout_seconds=proposal.timeout_seconds,
                retry_limit=proposal.retry_limit,
            )
            proposal.apply_status = PlannerProposalApplyStatus.APPLIED
            proposal.created_job_id = job.id
            proposal.updated_at = utc_now_iso()
            self.repository.update_proposal(proposal)
            state_changed = True
            applied_jobs.append(job)

        proposals = self.repository.list_plan_proposals(bundle.plan.id)
        if state_changed:
            bundle.plan.updated_at = utc_now_iso()
            bundle.plan.applied_at = bundle.plan.updated_at
            bundle.plan.status = self._derive_plan_status(bundle.plan.status, proposals)
            self.repository.update_plan(bundle.plan)

        return PlannerApplyResult(
            plan=bundle.plan,
            proposals=proposals,
            applied_jobs=applied_jobs,
            skipped_proposals=skipped_proposals,
        )

    def build_operation_context_summary(self, session_identifier: str):
        return self.runtime.build_operation_context_summary(session_identifier)

    def _write_back_memory_candidates(self, session_identifier: str) -> PlannerMemoryWritebackSummary:
        created_count = 0
        skipped_count = 0
        try:
            result = self.runtime.derive_memory_candidates(session_identifier)
            for candidate in result.candidates:
                if self._persist_candidate(session_identifier, candidate):
                    created_count += 1
            skipped_count = result.skipped_count
            return PlannerMemoryWritebackSummary(
                status=PlannerMemoryWritebackStatus.SUCCEEDED,
                created_count=created_count,
                skipped_count=skipped_count,
            )
        except Exception as exc:
            return PlannerMemoryWritebackSummary(
                status=PlannerMemoryWritebackStatus.FAILED,
                created_count=created_count,
                skipped_count=skipped_count,
                error_message=str(exc),
            )

    def _persist_candidate(
        self,
        session_identifier: str,
        candidate: PlannerDerivedMemoryCandidate,
    ) -> bool:
        self.memory_service.create_memory_entry(
            session_identifier=session_identifier,
            entry_type=candidate.entry_type,
            key=candidate.key,
            value=dict(candidate.value),
            summary=candidate.summary,
            source_job_identifier=candidate.source_job_identifier,
        )
        return True

    def _resolve_selection(
        self,
        proposals: list[PlannerProposal],
        selected_indices: list[int] | None,
    ) -> list[PlannerProposal]:
        pending = [
            proposal
            for proposal in proposals
            if proposal.apply_status == PlannerProposalApplyStatus.PENDING
        ]
        if selected_indices is None:
            return pending
        proposal_by_index = {proposal.proposal_index: proposal for proposal in proposals}
        resolved: list[PlannerProposal] = []
        for index in selected_indices:
            proposal = proposal_by_index.get(index)
            if proposal is None:
                raise ValueError(f"Unknown planner proposal index: {index}")
            resolved.append(proposal)
        return resolved

    def _derive_plan_status(
        self,
        current_status: PlannerPlanStatus,
        proposals: list[PlannerProposal],
    ) -> PlannerPlanStatus:
        proposed = [
            proposal
            for proposal in proposals
            if proposal.proposal_kind.value == "proposed"
        ]
        if not proposed:
            return current_status
        if all(proposal.apply_status == PlannerProposalApplyStatus.APPLIED for proposal in proposed):
            return PlannerPlanStatus.APPLIED
        if any(
            proposal.apply_status in {
                PlannerProposalApplyStatus.APPLIED,
                PlannerProposalApplyStatus.SKIPPED,
            }
            for proposal in proposed
        ):
            return PlannerPlanStatus.PARTIALLY_APPLIED
        return PlannerPlanStatus.PROPOSED
