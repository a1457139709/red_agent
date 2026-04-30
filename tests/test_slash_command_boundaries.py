import main as main_module
from main import ShellState
from models.session import SessionMode


def test_parse_slash_commands_require_command_boundary():
    assert main_module.parse_skill_command("/skillx list") is None
    assert main_module.parse_module_command("/modulex list") is None
    assert main_module.parse_job_command("/jobx list") is None
    assert main_module.parse_finding_command("/findingsx list") is None
    assert main_module.parse_artifact_command("/artifactsx list") is None
    assert main_module.parse_report_command("/reportsx list") is None
    assert main_module.parse_dashboard_command("/dashboardx") is None
    assert main_module.parse_planner_command("/plannerx plan S0001") is None
    assert main_module.parse_help_command("/helpful reports") is None
    assert main_module.parse_redteam_command("/redteamx") is None
    assert main_module.parse_normal_command("/normalx") is None


def test_redteam_prefixed_command_does_not_toggle_mode():
    shell_state = ShellState()
    outputs: list[str] = []
    errors: list[str] = []
    successes: list[str] = []

    handled = main_module.handle_redteam_command(
        "/redteamx",
        shell_state=shell_state,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert not handled
    assert shell_state.requested_session_mode == SessionMode.NORMAL
    assert outputs == []
    assert errors == []
    assert successes == []
