from io import StringIO
from pathlib import Path

from capabilities.loader import load_capability_from_file
from cli.ui import CliPresenter
from rich.console import Console
from models.checkpoint import CheckpointSummary
from models.run import Run, RunStatus, SessionLogEntry, SessionLogLevel
from models.skill import LoadedSkill, SkillManifest
from runtime.execution_events import ExecutionEventType, ExecutionProgressEvent


def build_presenter(outputs: list[str]) -> CliPresenter:
    return CliPresenter.for_callbacks(text_output=outputs.append)


def test_presenter_help_and_observation_render_clean_text():
    outputs: list[str] = []
    presenter = build_presenter(outputs)

    presenter.show_help()
    presenter.show_help("query")
    presenter.show_help("skill")
    presenter.show_help("artifact")
    presenter.show_help("report")
    presenter.show_help("module")
    presenter.show_observation(
        "line1\nline2\nline3\nline4\nline5",
        truncate_lines=3,
        truncate_chars=200,
    )

    assert "red-code" in outputs[0]
    assert "Natural-Language First" in outputs[0]
    assert "Advanced Help Topics" in outputs[0]
    assert "Summarize this repository structure" in outputs[0]
    assert "skill" in outputs[0]
    assert "query" in outputs[0]
    assert "operation" not in outputs[0]
    assert "job" not in outputs[0]
    assert "/help <topic>" in outputs[0]
    assert "The table above lists all supported topics." in outputs[0]
    assert "task" not in outputs[0]
    assert "/clear" in outputs[0]
    assert "/redteam [on|off|toggle|current]" in outputs[0]
    assert "Query Commands" in outputs[1]
    assert "/history [scope]" in outputs[1]
    assert "/report <session_summary|findings_summary|operator_report> [scope]" in outputs[1]
    assert "Skill Commands" in outputs[2]
    assert "Shorthand Invocation" in outputs[2]
    assert "/skill-name <prompt>" in outputs[2]
    assert "Artifact Commands" in outputs[3]
    assert "/artifact list <session_id> [limit]" in outputs[3]
    assert "/evidence" not in outputs[3]
    assert "Report Commands" in outputs[4]
    assert "/report show <report_id>" in outputs[4]
    assert "Module Commands" in outputs[5]
    assert "/module run <name> <target> [json_overrides]" in outputs[5]
    assert "line1" in outputs[6]
    assert "line3" in outputs[6]
    assert "[truncated for display]" in outputs[6]


def test_presenter_clear_screen_is_silent_for_callback_presenter():
    outputs: list[str] = []
    presenter = build_presenter(outputs)

    presenter.clear_screen()

    assert outputs == []


def test_presenter_clear_screen_uses_console_clear_in_default_mode():
    console = Console(file=StringIO(), force_terminal=False)
    called = {}

    def fake_clear(*, home=True):
        called["home"] = home

    console.clear = fake_clear
    presenter = CliPresenter(console=console)

    presenter.clear_screen()

    assert called == {"home": True}


def test_presenter_clear_screen_uses_cls_on_windows_tty(monkeypatch):
    class TtyBuffer(StringIO):
        def isatty(self) -> bool:
            return True

    console = Console(file=TtyBuffer(), force_terminal=False)
    called = {"system": [], "console_clear": 0}

    def fake_system(command: str) -> int:
        called["system"].append(command)
        return 0

    def fake_clear(*, home=True):
        called["console_clear"] += 1

    monkeypatch.setattr("cli.ui.os.name", "nt")
    monkeypatch.setattr("cli.ui.os.system", fake_system)
    console.clear = fake_clear
    presenter = CliPresenter(console=console)

    presenter.clear_screen()

    assert called == {"system": ["cls"], "console_clear": 0}


def test_presenter_detail_views_include_key_fields_without_blob_internals():
    outputs: list[str] = []
    presenter = build_presenter(outputs)
    session_label = "S0001"
    session_id = "session-uuid"
    run = Run(
        id="run-uuid",
        public_id="R0001",
        session_id=session_id,
        status=RunStatus.COMPLETED,
        step_count=2,
        last_usage={"total_tokens": 12},
        duration_ms=250,
        effective_skill_name="security-audit",
        effective_tools=["bash", "read_file"],
    )
    entry = SessionLogEntry(
        id="log-1",
        session_id=session_id,
        run_id=run.id,
        level=SessionLogLevel.INFO,
        message="tool_completed",
        payload={"tool_name": "read_file", "result_summary": "sample"},
    )
    checkpoint = CheckpointSummary(
        id="chk-123",
        session_id=session_id,
        run_id=run.id,
        created_at="2026-03-31T12:00:00+00:00",
        storage_kind="file_blob",
        payload_size_bytes=512,
        history_message_count=4,
        history_text_bytes=128,
        has_compressed_summary=True,
    )
    skill = LoadedSkill(
        manifest=SkillManifest(
            name="security-audit",
            description="Audit local code safely.",
            license="Proprietary",
            compatibility="Agent Skills baseline",
            allowed_tools=["read_file", "search"],
            metadata={"category": "security"},
            body="# Security Audit",
            user_invocable=True,
            shell="powershell",
        ),
        root_dir=Path("D:/skills/security-audit"),
        skill_file=Path("D:/skills/security-audit/SKILL.md"),
        source="built-in",
    )
    capability = load_capability_from_file(
        Path("src/capabilities/surface-recon/capability.json")
    )

    presenter.show_run_detail(run, session_label, [entry])
    presenter.show_checkpoint_detail(checkpoint, session_label, run.public_id)
    presenter.show_session_logs([entry], {run.id: run.public_id})
    presenter.show_skill_detail(skill)
    presenter.show_capability_list([capability], title="Modules")
    presenter.show_capability_detail(capability)
    presenter.show_skill_workflow_plan(
        skill_name="surface-recon",
        workflow_profile="surface-recon",
        session_label="S0001",
        primary_target="example.com",
        planned_rows=[
            {
                "type": "http_probe",
                "target": "https://example.com",
                "arguments": '{"method": "GET"}',
                "timeout": "-",
                "retry": "0",
                "notes": "Target is within the declared scope policy.",
            }
        ],
        skipped_rows=[
            {
                "type": "http_probe",
                "target": "http://example.com",
                "reason": "Protocol is not allowed.",
                "summary": "Probe http://example.com.",
            }
        ],
    )
    presenter.show_final_answer("Completed successfully.")
    presenter.show_error("Something failed.")
    presenter.show_success("Saved.")

    merged = "\n\n".join(outputs)
    assert "Session:" in merged and "S0001" in merged
    assert "Session Logs" in merged
    assert "Failure Kind:" in merged
    assert "Payload Size:" in merged
    assert "blob_path" not in merged
    assert "payload_digest" not in merged
    assert "Source:" in merged and "built-in" in merged
    assert "Invocation Mode:" in merged
    assert "Capability Detail" in merged and "surface-recon" in merged
    assert "Result Layers:" in merged
    assert "Skill Workflow Plan" in merged
    assert "Metadata" in merged and "category: security" in merged
    assert "Final Answer" in merged and "Completed successfully." in merged
    assert "Error" in merged and "Something failed." in merged
    assert "Success" in merged and "Saved." in merged


def test_presenter_tool_call_preserves_argument_types_in_display():
    outputs: list[str] = []
    presenter = build_presenter(outputs)

    presenter.show_tool_call("port_scan", {"target": "localhost", "ports": "[8080]"})
    presenter.show_tool_call("port_scan", {"target": "localhost", "ports": [8080]})

    assert '"[8080]"' in outputs[0]
    assert "[8080]" in outputs[1]


def test_presenter_renders_structured_execution_progress_events():
    outputs: list[str] = []
    presenter = build_presenter(outputs)

    presenter.show_execution_progress(
        ExecutionProgressEvent(
            event_type=ExecutionEventType.CONFIRMATION_REQUIRED,
            session_id="session-1",
            session_public_id="S0001",
            action_name="poc_execute",
            risk_level="dangerous",
            reason="requires approval",
            timestamp="2026-04-09T10:00:00+00:00",
        )
    )
    presenter.show_execution_progress(
        ExecutionProgressEvent(
            event_type=ExecutionEventType.CONFIRMATION_DENIED,
            session_id="session-1",
            session_public_id="S0001",
            action_name="poc_execute",
            risk_level="dangerous",
            timestamp="2026-04-09T10:00:00+00:00",
        )
    )
    presenter.show_execution_progress(
        ExecutionProgressEvent(
            event_type=ExecutionEventType.EXECUTION_STARTED,
            session_id="session-1",
            session_public_id="S0001",
            message="Foreground execution started.",
            timestamp="2026-04-09T10:00:00+00:00",
        )
    )
    presenter.show_execution_progress(
        ExecutionProgressEvent(
            event_type=ExecutionEventType.STEP_STARTED,
            session_id="session-1",
            session_public_id="S0001",
            step_type="tool",
            step_label="http_probe",
            timestamp="2026-04-09T10:00:01+00:00",
        )
    )
    presenter.show_execution_progress(
        ExecutionProgressEvent(
            event_type=ExecutionEventType.STEP_COMPLETED,
            session_id="session-1",
            session_public_id="S0001",
            step_type="tool",
            step_label="http_probe",
            message="ok",
            timestamp="2026-04-09T10:00:02+00:00",
        )
    )
    presenter.show_execution_progress(
        ExecutionProgressEvent(
            event_type=ExecutionEventType.EXECUTION_FAILED,
            session_id="session-1",
            session_public_id="S0001",
            message="boom",
            timestamp="2026-04-09T10:00:03+00:00",
        )
    )

    merged = "\n\n".join(outputs)
    assert "Confirmation Required" in merged
    assert "Confirmation Decision" in merged
    assert "Execution Started" in merged
    assert "session S0001 | http_probe started" in merged
    assert "Step Completed (S0001)" in merged
    assert "Execution Failed" in merged
