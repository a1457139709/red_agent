from agent.settings import Settings
from conftest import create_redteam_operation
from models.planner import (
    PlannerPlan,
    PlannerPlanStatus,
    PlannerProposal,
    PlannerProposalApplyStatus,
    PlannerProposalKind,
    PlannerSource,
)
from storage.repositories.planner import PlannerRepository
from storage.sqlite import SQLiteStorage


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_planner_repository_round_trip_and_updates(tmp_path):
    settings = build_settings(tmp_path)
    repository = PlannerRepository(SQLiteStorage(settings.sqlite_path))

    operation = create_redteam_operation(settings, title="Plan", objective="Persist planner state")
    plan = PlannerPlan.create(
        session_id=operation.id,
        planning_mode="next_steps",
        context_hash="abc123",
        summary="Planner summary.",
        rationale="Planner rationale.",
        planner_source=PlannerSource.FALLBACK,
    )
    proposal = PlannerProposal.create(
        plan_id=plan.id,
        proposal_index=1,
        proposal_kind=PlannerProposalKind.PROPOSED,
        job_type="http_probe",
        target_ref="https://example.com",
        arguments={"method": "GET"},
        summary="Probe https://example.com.",
        rationale="Web evidence suggests the endpoint is relevant.",
    )
    blocked = PlannerProposal.create(
        plan_id=plan.id,
        proposal_index=0,
        proposal_kind=PlannerProposalKind.BLOCKED,
        job_type="http_probe",
        target_ref="https://admin.example.net",
        summary="Blocked probe.",
        rationale="Out of scope target.",
        skip_reason="Target is explicitly denied by the scope policy.",
    )

    repository.create_plan(plan, [proposal, blocked])

    stored_plan = repository.get_plan(plan.public_id)
    assert stored_plan is not None
    assert stored_plan.public_id.startswith("PLN")
    stored_proposals = repository.list_plan_proposals(stored_plan.public_id)
    assert [item.job_type for item in stored_proposals] == ["http_probe", "http_probe"]
    assert stored_proposals[0].proposal_index == 1
    assert stored_proposals[1].proposal_kind == PlannerProposalKind.BLOCKED

    stored_plan.status = PlannerPlanStatus.PARTIALLY_APPLIED
    repository.update_plan(stored_plan)
    stored_proposals[0].apply_status = PlannerProposalApplyStatus.APPLIED
    stored_proposals[0].created_job_id = "job-1"
    repository.update_proposal(stored_proposals[0])

    refreshed_plan = repository.get_plan(stored_plan.public_id)
    refreshed_proposals = repository.list_plan_proposals(stored_plan.public_id)
    assert refreshed_plan is not None
    assert refreshed_plan.status == PlannerPlanStatus.PARTIALLY_APPLIED
    assert refreshed_proposals[0].apply_status == PlannerProposalApplyStatus.APPLIED
    assert refreshed_proposals[0].created_job_id == "job-1"
