from app.tool_access_policy_service import ToolAccessDecisionStatus, ToolAccessPolicyService
from models.session import SessionMode


def test_tool_access_policy_allows_normal_mode_base_tools(tmp_path):
    service = ToolAccessPolicyService()
    decision = service.evaluate_tool_access(
        mode=SessionMode.NORMAL,
        tool_name="bash",
        arguments={"command": "echo hello"},
        workspace=str(tmp_path),
        session_public_id="S0001",
    )
    assert decision.status == ToolAccessDecisionStatus.ALLOW


def test_tool_access_policy_blocks_redteam_shell_bypass(tmp_path):
    service = ToolAccessPolicyService()
    decision = service.evaluate_tool_access(
        mode=SessionMode.REDTEAM,
        tool_name="bash",
        arguments={"command": "nmap example.com"},
        workspace=str(tmp_path),
        session_public_id="S0001",
    )
    assert decision.status == ToolAccessDecisionStatus.DENY


def test_tool_access_policy_requires_confirmation_for_redteam_write_outside_session_area(tmp_path):
    service = ToolAccessPolicyService()
    decision = service.evaluate_tool_access(
        mode=SessionMode.REDTEAM,
        tool_name="write_file",
        arguments={"path": "notes.md"},
        workspace=str(tmp_path),
        session_public_id="S0001",
    )
    assert decision.status == ToolAccessDecisionStatus.CONFIRM


def test_tool_access_policy_allows_redteam_write_inside_session_area(tmp_path):
    service = ToolAccessPolicyService()
    session_file = tmp_path / ".red-code" / "sessions" / "S0001" / "notes.md"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    decision = service.evaluate_tool_access(
        mode=SessionMode.REDTEAM,
        tool_name="write_file",
        arguments={"path": str(session_file)},
        workspace=str(tmp_path),
        session_public_id="S0001",
    )
    assert decision.status == ToolAccessDecisionStatus.ALLOW
