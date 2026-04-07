import asyncio
from pathlib import Path
import textwrap

from langchain_core.messages import AIMessage

import main as main_module
from agent.settings import Settings
from agent.state import SessionState
from app.job_service import JobService
from app.operation_service import OperationService
from app.run_service import RunService
from app.skill_service import SkillService
from app.task_service import TaskService
from main import (
    ShellState,
    build_prompt,
    create_skill_service,
    handle_clear_command,
    handle_skill_command,
    handle_task_command,
    parse_skill_shorthand,
    run_interactive_shell,
)
from skills.registry import SkillRegistry
from runtime.task_runner import TaskRunner
from tools import build_tool_registry
from tools.executor import ToolExecutor


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def write_skill(root: Path, name: str, content: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return skill_file


def test_base_mode_prompt_and_task_create_blank_skill(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = create_skill_service()
    task_runner = TaskRunner(task_service, run_service, skill_service)
    session_state = SessionState()
    shell_state = ShellState()
    errors = []
    successes = []
    responses = iter(["Refactor loop", "Add explicit skill activation", ""])

    def fake_input(_prompt):
        return next(responses)

    assert build_prompt(shell_state) == "\n> "
    assert handle_task_command(
        "/task create",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        skill_service=skill_service,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    task = task_service.list_tasks(limit=1)[0]
    assert task.skill_profile is None
    assert successes
    assert not errors


def test_shell_skill_commands_and_prompt_rendering():
    shell_state = ShellState()
    skill_service = create_skill_service()
    outputs = []
    successes = []
    errors = []

    assert handle_skill_command(
        "/skill use security-audit",
        shell_state=shell_state,
        skill_service=skill_service,
        text_output=outputs.append,
        success_output=successes.append,
        error_output=errors.append,
    )
    assert shell_state.active_skill_name == "security-audit"
    assert build_prompt(shell_state) == "\nskill:security-audit > "

    assert handle_skill_command(
        "/skill current",
        shell_state=shell_state,
        skill_service=skill_service,
        text_output=outputs.append,
        success_output=successes.append,
        error_output=errors.append,
    )
    assert handle_skill_command(
        "/skill clear",
        shell_state=shell_state,
        skill_service=skill_service,
        text_output=outputs.append,
        success_output=successes.append,
        error_output=errors.append,
    )

    assert shell_state.active_skill_name is None
    assert any("Current skill: security-audit" in message for message in outputs)
    assert not errors


def test_parse_skill_shorthand_requires_known_skill():
    skill_service = create_skill_service()

    assert parse_skill_shorthand(
        "/security-audit inspect the configs",
        skill_service=skill_service,
    ) == ("security-audit", "inspect the configs")
    assert parse_skill_shorthand(
        "/git-auto-commit summarize and commit the current changes",
        skill_service=skill_service,
    ) == ("git-auto-commit", "summarize and commit the current changes")
    assert parse_skill_shorthand("/task list", skill_service=skill_service) is None
    assert parse_skill_shorthand("/unknown-skill demo", skill_service=skill_service) is None


def test_non_user_invocable_skill_cannot_be_activated(tmp_path):
    local_root = tmp_path / "skills"
    write_skill(
        local_root,
        "internal-only",
        """
        ---
        name: internal-only
        description: Internal skill.
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
        metadata:
          category: internal
        user-invocable: false
        ---

        # Internal Only
        """,
    )
    skill_service = SkillService(
        SkillRegistry.built_in_and_local(
            known_tool_names=set(build_tool_registry().keys()),
            local_root=local_root,
        )
    )
    errors = []

    assert handle_skill_command(
        "/skill use internal-only",
        shell_state=ShellState(),
        skill_service=skill_service,
        error_output=errors.append,
    )

    assert any("not user-invocable" in message for message in errors)


def test_handle_clear_command_resets_state_without_task_or_skill():
    session_state = SessionState()
    session_state.append_user_message("hello")
    session_state.compressed_summary = "summary"
    session_state.last_usage = {"total_tokens": 8}
    shell_state = ShellState()
    cleared = []

    assert handle_clear_command(
        "/clear",
        shell_state=shell_state,
        session_state=session_state,
        presenter=main_module.CliPresenter.for_callbacks(text_output=cleared.append),
    )

    assert session_state.history == []
    assert session_state.compressed_summary is None
    assert session_state.last_usage == {}
    assert shell_state.active_task_id is None
    assert shell_state.active_task_public_id is None
    assert shell_state.active_skill_name is None
    assert build_prompt(shell_state) == "\n> "
    assert cleared == []


def test_handle_clear_command_preserves_skill_and_task_binding():
    session_state = SessionState()
    session_state.append_user_message("hello")
    session_state.compressed_summary = "summary"
    session_state.last_usage = {"total_tokens": 8}
    shell_state = ShellState(
        active_task_id="task-1",
        active_task_public_id="T0001",
        active_skill_name="security-audit",
    )
    cleared = []

    assert handle_clear_command(
        "/clear",
        shell_state=shell_state,
        session_state=session_state,
        presenter=main_module.CliPresenter.for_callbacks(text_output=cleared.append),
    )

    assert session_state.history == []
    assert session_state.compressed_summary is None
    assert session_state.last_usage == {}
    assert shell_state.active_task_id == "task-1"
    assert shell_state.active_task_public_id == "T0001"
    assert shell_state.active_skill_name == "security-audit"
    assert build_prompt(shell_state) == "\ntask:T0001 > "
    assert cleared == []


def test_run_interactive_shell_supports_one_shot_skill_and_reset_clears_active_skill(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = create_skill_service()
    task_runner = TaskRunner(task_service, run_service, skill_service)
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"prompts": [], "answers": [], "headers": []}
    responses = iter(
        [
            "/skill use security-audit",
            "/security-audit inspect configs",
            "/reset",
            "/quit",
        ]
    )

    def fake_input(_prompt):
        return next(responses)

    async def fake_agent_loop(
        question,
        state,
        tool_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        captured["prompts"].append((question, system_prompt, [tool.name for tool in tools or []]))
        return {
            "status": "completed",
            "response": "done",
            "messages": [
                AIMessage(
                    content="done",
                    tool_calls=[],
                    usage_metadata={
                        "input_tokens": 4,
                        "output_tokens": 4,
                        "total_tokens": 8,
                    },
                )
            ],
            "usage": {"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
        }

    monkeypatch.setattr(main_module, "agent_loop", fake_agent_loop)
    monkeypatch.setattr(main_module.ColoredOutput, "print_final_answer", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_error", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_info", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_success", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_header", captured["headers"].append)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    question, system_prompt, tool_names = captured["prompts"][0]
    assert question == "inspect configs"
    assert "Security Audit" in system_prompt
    assert tool_names == ["bash", "list_dir", "read_file", "search"]
    assert shell_state.active_skill_name is None
    assert session_state.history == []
    assert any("Session reset" in header for header in captured["headers"])


def test_run_interactive_shell_blocks_workflow_only_skill_shorthand(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState()
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = create_skill_service(settings)
    task_runner = TaskRunner(task_service, run_service, skill_service)
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"answers": []}
    responses = iter([
        "/surface-recon example.com",
        "/quit",
    ])

    def fake_input(_prompt):
        return next(responses)

    monkeypatch.setattr(main_module.ColoredOutput, "print_final_answer", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_error", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_info", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_success", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_header", lambda _message: None)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    assert any("disables direct model invocation" in message for message in captured["answers"])


def test_skill_plan_previews_bounded_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    skill_service = create_skill_service(settings)
    outputs = []
    errors = []

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect example.com",
        allowed_hosts=["example.com"],
        allowed_ports=[443],
        allowed_protocols=["https", "tls"],
        allowed_tool_categories=["recon"],
    )
    responses = iter([
        "example.com",
        "{}",
    ])

    def fake_input(_prompt):
        return next(responses)

    assert handle_skill_command(
        f"/skill plan web-enum {operation.public_id}",
        shell_state=ShellState(),
        skill_service=skill_service,
        operation_service=operation_service,
        job_service=job_service,
        text_output=outputs.append,
        error_output=errors.append,
        input_func=fake_input,
    )

    merged = "\n\n".join(outputs)
    assert "Skill Workflow Plan" in merged
    assert "web-enum" in merged
    assert "https://example.com" in merged
    assert "Skipped Jobs" in merged
    assert not errors


def test_skill_apply_creates_jobs(tmp_path):
    settings = build_settings(tmp_path)
    operation_service = OperationService.from_settings(settings)
    job_service = JobService.from_settings(settings)
    skill_service = create_skill_service(settings)
    outputs = []
    errors = []
    successes = []

    operation = operation_service.create_operation(
        title="Recon",
        objective="Inspect example.com",
        allowed_hosts=["example.com", "8.8.8.8"],
        allowed_tool_categories=["recon"],
    )
    responses = iter([
        "example.com",
        "{}",
        "yes",
    ])

    def fake_input(_prompt):
        return next(responses)

    assert handle_skill_command(
        f"/skill apply surface-recon {operation.public_id}",
        shell_state=ShellState(),
        skill_service=skill_service,
        operation_service=operation_service,
        job_service=job_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    jobs = job_service.list_jobs(operation.id, limit=10)
    assert len(jobs) == 4
    assert any("Created 4 job(s) from skill surface-recon" in message for message in successes)
    assert not errors


def test_run_interactive_shell_clear_preserves_active_skill_and_clears_screen(
    monkeypatch,
    tmp_path,
):
    settings = build_settings(tmp_path)
    session_state = SessionState()
    shell_state = ShellState(active_skill_name="security-audit")
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = create_skill_service()
    task_runner = TaskRunner(task_service, run_service, skill_service)
    tool_executor = ToolExecutor(build_tool_registry())
    captured = {"prompts": [], "clears": 0, "answers": []}
    responses = iter([
        "/clear",
        "inspect configs",
        "/quit",
    ])

    def fake_input(_prompt):
        return next(responses)

    async def fake_agent_loop(
        question,
        state,
        tool_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        captured["prompts"].append((question, system_prompt, [tool.name for tool in tools or []]))
        return {
            "status": "completed",
            "response": "done",
            "messages": [
                AIMessage(
                    content="done",
                    tool_calls=[],
                    usage_metadata={
                        "input_tokens": 4,
                        "output_tokens": 4,
                        "total_tokens": 8,
                    },
                )
            ],
            "usage": {"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
        }

    monkeypatch.setattr(main_module, "agent_loop", fake_agent_loop)
    monkeypatch.setattr(main_module.ColoredOutput, "clear_screen", lambda: captured.__setitem__("clears", captured["clears"] + 1))
    monkeypatch.setattr(main_module.ColoredOutput, "print_final_answer", captured["answers"].append)
    monkeypatch.setattr(main_module.ColoredOutput, "print_error", captured["answers"].append)

    asyncio.run(
        run_interactive_shell(
            settings=settings,
            session_state=session_state,
            shell_state=shell_state,
            tool_executor=tool_executor,
            task_service=task_service,
            run_service=run_service,
            task_runner=task_runner,
            skill_service=skill_service,
            input_func=fake_input,
        )
    )

    question, system_prompt, tool_names = captured["prompts"][0]
    assert question == "inspect configs"
    assert "Security Audit" in system_prompt
    assert tool_names == ["bash", "list_dir", "read_file", "search"]
    assert captured["clears"] == 1
    assert shell_state.active_skill_name == "security-audit"
    assert build_prompt(shell_state) == "\nskill:security-audit > "
