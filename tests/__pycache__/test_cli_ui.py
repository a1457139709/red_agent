from pathlib import Path

from cli.ui import CliPresenter
from models.checkpoint import CheckpointSummary
from models.run import Run, RunStatus, TaskLogEntry, TaskLogLevel
from models.skill import LoadedSkill, SkillManifest
from models.task import Task, TaskStatus


def build_presenter(outputs: list[str]) -> CliPresenter:
    return CliPresenter.for_callbacks(text_output=outputs.append)


def test_presenter_help_and_observation_render_clean_text():
    outputs: list[str] = []
    presenter = build_presenter(outputs)

    presenter.show_help()
    presenter.show_help("task")
    presenter.show_help("skill")
    presenter.show_observation(
        "line1\nline2\nline3\nline4\nline5",
        truncate_lines=3,
        truncate_chars=200,
    )

    assert "mini-claude-code" in outputs[0]
    assert "Help Topics" in outputs[0]
    assert "task" in outputs[0]
    assert "skill" in outputs[0]
    assert "/help task" in outputs[0]
    assert "/help skill" in outputs[0]
    assert "Task Commands" in outputs[1]
    assert "Runs and Checkpoints" in outputs[1]
    assert "latest' or 'last" in outputs[1]
    assert "Skill Commands" in outputs[2]
    assert "Shorthand Invocation" in outputs[2]
    assert "/skill-name <prompt>" in outputs[2]
    assert "line1" in outputs[3]
    assert "line3" in outputs[3]
    assert "[truncated for display]" in outputs[3]


def test_presenter_detail_views_include_key_fields_without_blob_internals():
    outputs: list[str] = []
    presenter = build_presenter(outputs)
    task = Task(
        id="task-uuid",
        public_id="T0001",
        title="Refactor loop",
        goal="Improve CLI readability",
        workspace="D:/workspace",
        status=TaskStatus.PAUSED,
        skill_profile="security-audit",
        last_checkpoint="chk-123",
    )
    run = Run(
        id="run-uuid",
        public_id="R0001",
        task_id=task.id,
        status=RunStatus.COMPLETED,
        step_count=2,
        last_usage={"total_tokens": 12},
        duration_ms=250,
        effective_skill_name="security-audit",
        effective_tools=["bash", "read_file"],
    )
    entry = TaskLogEntry(
        id="log-1",
        task_id=task.id,
        run_id=run.id,
        level=TaskLogLevel.INFO,
        message="tool_completed",
        payload={"tool_name": "read_file", "result_summary": "sample"},
    )
    checkpoint = CheckpointSummary(
        id="chk-123",
        task_id=task.id,
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
        ),
        root_dir=Path("D:/skills/security-audit"),
        skill_file=Path("D:/skills/security-audit/SKILL.md"),
        source="built-in",
    )

    presenter.show_task_detail(task)
    presenter.show_run_detail(run, task, [entry])
    presenter.show_checkpoint_detail(checkpoint, task, run.public_id)
    presenter.show_skill_detail(skill)
    presenter.show_final_answer("Completed successfully.")
    presenter.show_error("Something failed.")
    presenter.show_success("Saved.")

    merged = "\n\n".join(outputs)
    assert "Task ID:" in merged and "T0001" in merged
    assert "Failure Kind:" in merged
    assert "Payload Size:" in merged
    assert "blob_path" not in merged
    assert "payload_digest" not in merged
    assert "Source:" in merged and "built-in" in merged
    assert "Metadata" in merged and "category: security" in merged
    assert "Final Answer" in merged and "Completed successfully." in merged
    assert "Error" in merged and "Something failed." in merged
    assert "Success" in merged and "Saved." in merged
