from pathlib import Path

import pytest

from agent.settings import Settings
from app.job_service import JobService
from app.operation_service import OperationService
from app.skill_workflow_service import SkillWorkflowService
from main import create_skill_service


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_surface_recon_plans_hostname_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    skill_service = create_skill_service(settings)
    workflow_service = SkillWorkflowService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Surface recon",
        objective="Inspect attack surface",
        allowed_hosts=["example.com", "8.8.8.8"],
        allowed_tool_categories=["recon"],
    )

    plan = workflow_service.plan_workflow(
        skill=skill_service.require_skill("surface-recon"),
        operation_identifier=operation.id,
        primary_target="example.com",
    )

    assert [job.job_type for job in plan.planned_jobs] == [
        "dns_lookup",
        "http_probe",
        "http_probe",
        "tls_inspect",
    ]
    assert [job.target_ref for job in plan.planned_jobs] == [
        "example.com",
        "http://example.com",
        "https://example.com",
        "example.com:443",
    ]
    assert plan.skipped_jobs == []


def test_web_enum_strips_input_path_and_generates_bounded_targets(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    skill_service = create_skill_service(settings)
    workflow_service = SkillWorkflowService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Web enum",
        objective="Inspect web endpoints",
        allowed_hosts=["example.com"],
        allowed_ports=[443],
        allowed_protocols=["https", "tls"],
        allowed_tool_categories=["recon"],
    )

    plan = workflow_service.plan_workflow(
        skill=skill_service.require_skill("web-enum"),
        operation_identifier=operation.id,
        primary_target="https://example.com/login?next=/admin",
    )

    assert [job.target_ref for job in plan.planned_jobs] == [
        "https://example.com",
        "https://example.com/robots.txt",
        "https://example.com/.well-known/security.txt",
        "example.com:443",
    ]
    assert all(not target.endswith("/login?next=/admin") for target in [job.target_ref for job in plan.planned_jobs])


def test_web_enum_filters_out_disallowed_protocols(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    skill_service = create_skill_service(settings)
    workflow_service = SkillWorkflowService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Web enum",
        objective="Inspect web endpoints",
        allowed_hosts=["example.com"],
        allowed_ports=[443],
        allowed_protocols=["https", "tls"],
        allowed_tool_categories=["recon"],
    )

    plan = workflow_service.plan_workflow(
        skill=skill_service.require_skill("web-enum"),
        operation_identifier=operation.id,
        primary_target="example.com",
    )

    assert all(
        job.target_ref.startswith("https://") or job.job_type == "tls_inspect"
        for job in plan.planned_jobs
    )
    assert any(skipped.target_ref.startswith("http://") for skipped in plan.skipped_jobs)


def test_skill_workflow_service_raises_when_no_jobs_are_in_scope(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    skill_service = create_skill_service(settings)
    workflow_service = SkillWorkflowService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Blocked",
        objective="Reject recon",
        allowed_hosts=["example.com"],
        allowed_tool_categories=["http"],
    )

    with pytest.raises(ValueError, match="produced no in-scope jobs"):
        workflow_service.plan_workflow(
            skill=skill_service.require_skill("surface-recon"),
            operation_identifier=operation.id,
            primary_target="example.com",
        )


def test_apply_plan_persists_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    skill_service = create_skill_service(settings)
    workflow_service = SkillWorkflowService.from_settings(settings)

    operation = operation_service.create_operation(
        title="Apply",
        objective="Persist plan",
        allowed_hosts=["example.com", "8.8.8.8"],
        allowed_tool_categories=["recon"],
    )
    plan = workflow_service.plan_workflow(
        skill=skill_service.require_skill("surface-recon"),
        operation_identifier=operation.id,
        primary_target="example.com",
    )

    created_jobs = workflow_service.apply_plan(plan)

    assert len(created_jobs) == len(plan.planned_jobs)
    persisted_job_types = [job.job_type for job in job_service.list_jobs(operation.id, limit=10)]
    assert sorted(persisted_job_types) == ["dns_lookup", "http_probe", "http_probe", "tls_inspect"]
