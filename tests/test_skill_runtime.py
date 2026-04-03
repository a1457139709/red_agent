from pathlib import Path
import asyncio
import textwrap

import pytest
from langchain_core.messages import AIMessage

from agent.prompt import assemble_system_prompt
from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.skill_service import DEFAULT_SKILL_NAME, SkillService
from app.task_service import TaskService
from main import ShellState, create_skill_service, handle_skill_command, handle_task_command
from models.run import TaskLogLevel
from models.skill import SkillLoadError
from runtime.task_runner import TaskRunner
from skills.loader import load_skill_from_file
from skills.registry import SkillRegistry
from tools import build_tool_registry
from tools.executor import ToolExecutor
import runtime.task_runner as task_runner_module


class FakeTool:
    name = "fake_tool"

    def invoke(self, args):
        return "ok"


def build_settings(tmp_path: Path) -> Settings:
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


def test_load_skill_parses_required_fields_and_extensions(tmp_path):
    skill_file = write_skill(
        tmp_path,
        "demo-skill",
        """
        ---
        name: demo-skill
        description: Test skill for parsing and runtime loading.
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
          - search
        metadata:
          category: demo
          risk_level: low
        user-invocable: true
        shell: powershell
        extra-note: keep
        ---

        # Demo Skill

        Use this prompt body.
        """,
    )
    references_dir = skill_file.parent / "references"
    references_dir.mkdir()
    (references_dir / "checklist.md").write_text("demo", encoding="utf-8")
    scripts_dir = skill_file.parent / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "scan.py").write_text("print('ok')", encoding="utf-8")

    loaded = load_skill_from_file(skill_file)

    assert loaded.manifest.name == "demo-skill"
    assert loaded.manifest.allowed_tools == ["read_file", "search"]
    assert loaded.manifest.metadata["category"] == "demo"
    assert loaded.manifest.user_invocable is True
    assert loaded.manifest.shell == "powershell"
    assert loaded.manifest.raw_frontmatter["extra-note"] == "keep"
    assert loaded.manifest.references[0].name == "checklist.md"
    assert loaded.manifest.scripts[0].name == "scan.py"


def test_load_skill_rejects_nested_frontmatter(tmp_path):
    skill_file = write_skill(
        tmp_path,
        "bad-skill",
        """
        ---
        name: bad-skill
        description: Invalid skill
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
        metadata:
          nested:
            child: true
        ---

        # Invalid
        """,
    )

    with pytest.raises(SkillLoadError):
        load_skill_from_file(skill_file)


def test_registry_rejects_mismatched_names_and_unknown_tools(tmp_path):
    write_skill(
        tmp_path,
        "wrong-dir",
        """
        ---
        name: other-name
        description: Invalid mismatch
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - read_file
        metadata:
          category: demo
        ---

        # Wrong
        """,
    )

    registry = SkillRegistry(tmp_path, known_tool_names=set(build_tool_registry().keys()))
    with pytest.raises(SkillLoadError):
        registry.list_skills()

    mismatch_file = tmp_path / "wrong-dir" / "SKILL.md"
    mismatch_file.unlink()
    (tmp_path / "wrong-dir").rmdir()

    write_skill(
        tmp_path,
        "unknown-tool",
        """
        ---
        name: unknown-tool
        description: Invalid tool list
        license: Proprietary
        compatibility: Agent Skills baseline
        allowed-tools:
          - not_real
        metadata:
          category: demo
        ---

        # Wrong
        """,
    )
    registry = SkillRegistry(tmp_path, known_tool_names=set(build_tool_registry().keys()))
    with pytest.raises(SkillLoadError):
        registry.list_skills()


def test_skill_service_resolves_default_skill_and_prompt_order():
    registry = SkillRegistry.built_in(known_tool_names=set(build_tool_registry().keys()))
    service = SkillService(registry)

    skill = service.resolve_skill(None)
    runtime_config = asyncio.run(
        service.build_runtime_config(
            skill_name=None,
            context_summary="compressed session summary",
        )
    )
    print("allowed_tools:")
    for tool in runtime_config.allowed_tools:
        print(tool)
    assert skill.manifest.name == DEFAULT_SKILL_NAME
    assert "web_fetch" in runtime_config.allowed_tools
    assert "web_search" in runtime_config.allowed_tools
    skill_index = runtime_config.system_prompt.index("# Skill Instructions")
    context_index = runtime_config.system_prompt.index("# Context Summary")
    assert skill_index < context_index
    assert "compressed session summary" in runtime_config.system_prompt
    assert "Development Default" in runtime_config.system_prompt


def test_git_auto_commit_skill_is_discovered_with_expected_runtime_metadata():
    skill_service = create_skill_service()

    skill = skill_service.require_skill("git-auto-commit")

    assert skill.manifest.user_invocable is True
    assert skill.manifest.shell == "powershell"
    assert skill.manifest.allowed_tools == ["bash", "list_dir", "read_file", "search"]
    assert "git status --short" in skill.manifest.body
    assert "git commit -m" in skill.manifest.body


def test_assemble_system_prompt_supports_legacy_extra_prompt():
    prompt = asyncio.run(assemble_system_prompt("legacy summary"))

    assert "# Context Summary" in prompt
    assert "legacy summary" in prompt


# def test_system_prompt_contains_new_sections_and_no_legacy_corruption():
#     prompt = asyncio.run(assemble_system_prompt())

#     assert "# Identity and Role" in prompt
#     assert "# Primary Objectives" in prompt
#     assert "# Operating Rules" in prompt
#     assert "# Tool Use Rules" in prompt
#     assert "# Safety and Permission Rules" in prompt
#     assert "# Task and Skill Awareness" in prompt
#     assert "# Response Behavior" in prompt
#     assert "# Editing Discipline" in prompt
#     assert "# Failure and Recovery Behavior" in prompt
#     assert "# Hard Constraints" in prompt
#     assert "You are `red-code`" in prompt
#     assert "Reply in English by default." in prompt
#     assert "user's" in prompt
#     assert "???" not in prompt
#     assert "??????" not in prompt
#     assert "?" not in prompt


def test_handle_skill_commands_and_task_create_with_default_skill(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = SkillService(
        SkillRegistry.built_in(known_tool_names=set(build_tool_registry().keys()))
    )
    task_runner = TaskRunner(task_service, run_service, skill_service)
    shell_state = ShellState()
    session_state = SessionState()
    outputs = []
    errors = []
    successes = []
    responses = iter(["Refactor loop", "Add skill runtime", ""])

    def fake_input(_prompt):
        return next(responses)

    assert handle_skill_command(
        "/skill list",
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_skill_command(
        "/skill show development-default",
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_task_command(
        "/task create",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        skill_service=skill_service,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    task = task_service.list_tasks(limit=1)[0]

    assert task.skill_profile == DEFAULT_SKILL_NAME
    assert any("development-default" in message for message in outputs)
    assert successes
    assert not errors


def test_handle_task_create_rejects_invalid_skill(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = SkillService(
        SkillRegistry.built_in(known_tool_names=set(build_tool_registry().keys()))
    )
    task_runner = TaskRunner(task_service, run_service, skill_service)
    shell_state = ShellState()
    session_state = SessionState()
    errors = []
    responses = iter(["Task", "Goal", "missing-skill"])

    def fake_input(_prompt):
        return next(responses)

    assert handle_task_command(
        "/task create",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        skill_service=skill_service,
        error_output=errors.append,
        input_func=fake_input,
    )

    assert errors
    assert task_service.list_tasks() == []


def test_task_runner_uses_bound_skill_and_marks_missing_skill_failures(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    skill_service = SkillService(
        SkillRegistry.built_in(known_tool_names=set(build_tool_registry().keys()))
    )
    runner = TaskRunner(task_service, run_service, skill_service)
    task = task_service.create_task(
        title="Audit",
        goal="Review the project",
        skill_profile="security-audit",
    )
    task, session_state = runner.resume_task(task.id)
    executor = ToolExecutor(build_tool_registry())
    seen_tool_names = []

    async def fake_agent_loop(
        question,
        state,
        tool_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        seen_tool_names.extend(tool.name for tool in tools or [])
        assert "Security Audit" in system_prompt
        return {
            "status": "completed",
            "response": "done",
            "messages": [
                AIMessage(
                    content="done",
                    tool_calls=[],
                    usage_metadata={
                        "input_tokens": 6,
                        "output_tokens": 6,
                        "total_tokens": 12,
                    },
                )
            ],
            "usage": {"input_tokens": 6, "output_tokens": 6, "total_tokens": 12},
        }

    monkeypatch.setattr(task_runner_module, "agent_loop", fake_agent_loop)

    result = asyncio.run(
        runner.run_prompt(
            task_id=task.id,
            question="continue",
            session_state=session_state,
            tool_executor=executor,
            settings=settings,
        )
    )

    assert result["status"] == "completed"
    assert seen_tool_names == ["bash", "list_dir", "read_file", "search"]

    broken_task = task_service.create_task(
        title="Broken",
        goal="Review",
        skill_profile="missing-skill",
    )
    with pytest.raises(SkillLoadError):
        asyncio.run(
            runner.run_prompt(
                task_id=broken_task.id,
                question="continue",
                session_state=SessionState(),
                tool_executor=executor,
                settings=settings,
            )
        )

    failed_task = task_service.require_task(broken_task.id)
    logs = run_service.list_logs(broken_task.id)

    assert failed_task.status.value == "failed"
    assert "missing-skill" in failed_task.last_error
    assert any(entry.level == TaskLogLevel.ERROR and entry.message == "run_failed" for entry in logs)
