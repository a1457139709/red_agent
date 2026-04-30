import main as main_module
from agent.settings import Settings
from app.artifact_service import ArtifactService
from app.finding_service import FindingService
from app.report_service import ReportService
from app.session_service import SessionService
from main import ShellState


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def build_services(tmp_path):
    settings = build_settings(tmp_path)
    return (
        SessionService.from_settings(settings),
        ArtifactService.from_settings(settings),
        FindingService.from_settings(settings),
        ReportService.from_settings(settings),
    )


def test_plural_resource_lists_default_to_active_session(tmp_path):
    session_service, artifact_service, finding_service, report_service = build_services(tmp_path)
    session = session_service.create_session(
        title="Active",
        goal="Inspect records",
        mode="redteam",
        status="active",
    )
    shell_state = ShellState(active_session_public_id=session.public_id)
    outputs: list[str] = []
    errors: list[str] = []

    assert main_module.handle_finding_command(
        "/findings",
        finding_service=finding_service,
        shell_state=shell_state,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert main_module.handle_artifact_command(
        "/artifacts",
        artifact_service=artifact_service,
        finding_service=finding_service,
        shell_state=shell_state,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert main_module.handle_report_command(
        "/reports",
        report_service=report_service,
        artifact_service=artifact_service,
        finding_service=finding_service,
        shell_state=shell_state,
        text_output=outputs.append,
        error_output=errors.append,
    )

    assert errors == []
    assert any("No findings found." in output for output in outputs)
    assert any("No artifacts found." in output for output in outputs)
    assert any("No reports found." in output for output in outputs)


def test_plural_resource_lists_require_active_session_without_scope(tmp_path):
    _session_service, _artifact_service, finding_service, _report_service = build_services(tmp_path)
    errors: list[str] = []

    assert main_module.handle_finding_command(
        "/findings",
        finding_service=finding_service,
        shell_state=ShellState(),
        error_output=errors.append,
    )

    assert len(errors) == 1
    assert "No active session." in errors[0]
