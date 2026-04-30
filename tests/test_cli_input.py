from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.capability_service import CapabilityService
from app.finding_service import FindingService
from app.module_service import ModuleService
from app.planner_service import PlannerService
from app.report_service import ReportService
from app.session_service import SessionService
from cli.input import (
    CompletionContext,
    shell_history_path,
    suggest_command_completions,
)
from main import ShellState, create_capability_service
from models.planner import PlannerPlan, PlannerProposal, PlannerProposalKind, PlannerSource
from models.session import SessionMode


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_completion_context(tmp_path) -> tuple[CompletionContext, dict[str, str]]:
    settings = build_settings(tmp_path)
    session_service = SessionService.from_settings(settings)
    capability_service = create_capability_service(settings)
    module_service = ModuleService(capability_service)
    artifact_service = ArtifactService.from_settings(settings)
    finding_service = FindingService.from_settings(settings)
    report_service = ReportService.from_settings(settings)
    planner_service = PlannerService.from_settings(settings)

    session = session_service.create_session(
        title="Completion Session",
        goal="Exercise CLI completion",
        mode=SessionMode.REDTEAM,
        status="active",
    )
    artifact = artifact_service.create_artifact(
        session_identifier=session.public_id,
        artifact_type="http_response",
        target_ref="https://example.com",
        title="HTTP response",
        summary="Captured response.",
    )
    finding = finding_service.create_finding(
        session_identifier=session.public_id,
        finding_type="reachable_service",
        title="Reachable service",
        target_ref="https://example.com",
        severity="medium",
        confidence="high",
        summary="Responded successfully.",
    )
    report = report_service.create_report(
        session_identifier=session.public_id,
        report_type="session_summary",
        title="Session summary",
        summary="Summarize the session.",
    )
    plan = PlannerPlan.create(
        session_id=session.id,
        planning_mode="redteam",
        context_hash="hash",
        summary="Plan summary",
        rationale="Plan rationale",
        planner_source=PlannerSource.FALLBACK,
    )
    proposal = PlannerProposal.create(
        plan_id=plan.id,
        proposal_index=1,
        proposal_kind=PlannerProposalKind.PROPOSED,
        job_type="http_probe",
        target_ref="https://example.com",
    )
    planner_service.repository.create_plan(plan, [proposal])

    context = CompletionContext(
        settings=settings,
        shell_state=ShellState(
            active_session_id=session.id,
            active_session_public_id=session.public_id,
            active_session_mode=SessionMode.REDTEAM,
        ),
        capability_service=capability_service,
        module_service=module_service,
        session_service=session_service,
        artifact_service=artifact_service,
        finding_service=finding_service,
        report_service=report_service,
        planner_service=planner_service,
    )
    ids = {
        "session": session.public_id,
        "artifact": artifact.public_id,
        "finding": finding.public_id,
        "report": report.public_id,
        "plan": plan.public_id,
    }
    return context, ids


def completion_texts(text: str, context: CompletionContext) -> list[str]:
    return [suggestion.text for suggestion in suggest_command_completions(text, context)]


def test_shell_history_path_uses_workspace_app_data(tmp_path):
    settings = build_settings(tmp_path)

    assert shell_history_path(settings) == tmp_path / ".red-code" / "history"


def test_slash_completion_includes_top_level_commands_and_help_topics(tmp_path):
    context, _ids = build_completion_context(tmp_path)

    assert "/help" in completion_texts("/", context)
    assert "reports" in completion_texts("/help r", context)


def test_slash_completion_includes_dynamic_skills_and_modules(tmp_path):
    context, _ids = build_completion_context(tmp_path)

    assert "security-audit" in completion_texts("/skill use security", context)
    assert "surface-recon" in completion_texts("/module run surface", context)
    assert "/security-audit" in completion_texts("/security", context)


def test_slash_completion_includes_resource_and_session_ids(tmp_path):
    context, ids = build_completion_context(tmp_path)

    assert ids["session"] in completion_texts("/history S", context)
    assert ids["artifact"] in completion_texts("/artifacts show A", context)
    assert ids["finding"] in completion_texts("/findings confirm F", context)
    assert ids["finding"] in completion_texts("/why F", context)
    assert ids["report"] in completion_texts("/reports show R", context)
    assert ids["artifact"] in completion_texts("/show A", context)


def test_slash_completion_includes_report_types_and_planner_arguments(tmp_path):
    context, ids = build_completion_context(tmp_path)

    assert "operator_report" in completion_texts("/reports generate operator", context)
    assert ids["plan"] in completion_texts("/planner apply PLN", context)
    assert "1" in completion_texts(f"/planner apply {ids['plan']} ", context)
