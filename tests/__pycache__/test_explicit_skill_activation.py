import asyncio

from langchain_core.messages import AIMessage

import main as main_module
from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.task_service import TaskService
from main import (
    ShellState,
    build_prompt,
    create_skill_service,
    handle_skill_command,
    handle_task_command,
    parse_skill_shorthand,
    run_interactive_shell,
)
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
    assert parse_skill_shorthand("/task list", skill_service=skill_service) is None
    assert parse_skill_shorthand("/unknown-skill demo", skill_service=skill_service) is None


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
