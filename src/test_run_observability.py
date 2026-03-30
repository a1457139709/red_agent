from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage

import main as main_module
import runtime.task_runner as task_runner_module
from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.task_service import TaskService
from models.run import RunFailureKind, RunStatus, TaskLogLevel
from models.task import TaskStatus
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


class FailingTool:
    name = "failing_tool"

    def invoke(self, args):
        raise RuntimeError("tool boom")


def test_run_service_assigns_public_ids_and_supports_lookup(tmp_path):
    settings = build_settings(tmp_path)
    run_service = RunService.from_settings(settings)
    task_service = TaskService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")

    first = run_service.start_run(task.id)
    second = run_service.start_run(task.id)

    assert first.public_id == "R0001"
    assert second.public_id == "R0002"
    assert run_service.require_run(first.public_id).id == first.id
    assert run_service.require_run(first.id[:8]).id == first.id


def test_run_repository_backfills_missing_public_ids(tmp_path):
    settings = build_settings(tmp_path)
    run_service = RunService.from_settings(settings)
    task_service = TaskService.from_settings(settings)
    task = task_service.create_task(title="Task", goal="Goal")
    run = run_service.start_run(task.id)

    with run_service.repository.storage.connect() as connection:
        connection.execute("UPDATE runs SET public_id = '' WHERE id = ?", (run.id,))
        connection.commit()

    refreshed = RunService.from_settings(settings)
    backfilled = refreshed.require_run(run.id)

    assert backfilled.public_id == "R0001"


def test_task_runner_records_tool_events_and_run_metadata(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service, main_module.create_skill_service(settings))
    tool_executor = ToolExecutor(build_tool_registry())
    task = task_service.create_task(title="Task", goal="Goal", skill_profile="security-audit")
    task, session_state = runner.resume_task(task.id)
    (tmp_path / "sample.txt").write_text("hello\n", encoding="utf-8")

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        result = runtime_executor.execute("read_file", {"file_path": "sample.txt"})
        return {
            "status": "completed",
            "response": result,
            "messages": [
                AIMessage(
                    content=result,
                    tool_calls=[],
                    usage_metadata={"input_tokens": 3, "output_tokens": 3, "total_tokens": 6},
                )
            ],
            "usage": {"input_tokens": 3, "output_tokens": 3, "total_tokens": 6},
        }

    monkeypatch.setattr(task_runner_module, "agent_loop", fake_agent_loop)

    asyncio.run(
        runner.run_prompt(
            task_id=task.id,
            question="read it",
            session_state=session_state,
            tool_executor=tool_executor,
            settings=settings,
        )
    )

    run = run_service.list_runs(task.id, limit=1)[0]
    run_logs = run_service.list_run_logs(run.public_id, limit=20)
    log_messages = {entry.message for entry in run_logs}

    assert run.public_id == "R0001"
    assert run.status == RunStatus.COMPLETED
    assert run.duration_ms is not None
    assert run.effective_skill_name == "security-audit"
    assert run.effective_tools == ["bash", "list_dir", "read_file", "search"]
    assert "tool_invoked" in log_messages
    assert "tool_completed" in log_messages


def test_task_runner_classifies_tool_error(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service)
    task = task_service.create_task(title="Task", goal="Goal")
    task, session_state = runner.resume_task(task.id)
    tool_executor = ToolExecutor({"failing_tool": FailingTool()})

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        runtime_executor.execute("failing_tool", {"value": 1})
        return {"status": "completed", "response": "never", "messages": [], "usage": {}}

    monkeypatch.setattr(task_runner_module, "agent_loop", fake_agent_loop)

    try:
        asyncio.run(
            runner.run_prompt(
                task_id=task.id,
                question="boom",
                session_state=session_state,
                tool_executor=tool_executor,
                settings=settings,
            )
        )
    except Exception:
        pass

    run = run_service.list_runs(task.id, limit=1)[0]

    assert run.status == RunStatus.FAILED
    assert run.failure_kind == RunFailureKind.TOOL_ERROR.value
    assert run.last_error == "tool boom"


def test_task_runner_marks_max_steps_exceeded_on_completed_run(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service)
    task = task_service.create_task(title="Task", goal="Goal")
    task, session_state = runner.resume_task(task.id)
    tool_executor = ToolExecutor(build_tool_registry())

    async def fake_agent_loop(
        question,
        state,
        runtime_executor,
        current_settings,
        *,
        system_prompt=None,
        tools=None,
    ):
        return {
            "status": "max_steps_exceeded",
            "response": "too many steps",
            "messages": [],
            "usage": {"total_tokens": 10},
        }

    monkeypatch.setattr(task_runner_module, "agent_loop", fake_agent_loop)

    result = asyncio.run(
        runner.run_prompt(
            task_id=task.id,
            question="continue",
            session_state=session_state,
            tool_executor=tool_executor,
            settings=settings,
        )
    )

    run = run_service.list_runs(task.id, limit=1)[0]
    updated_task = task_service.require_task(task.id)

    assert result["status"] == "max_steps_exceeded"
    assert run.status == RunStatus.COMPLETED
    assert run.failure_kind == RunFailureKind.MAX_STEPS_EXCEEDED.value
    assert updated_task.status == TaskStatus.RUNNING


def test_task_cli_renders_runs_run_detail_and_task_logs(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service, main_module.create_skill_service(settings))
    shell_state = main_module.ShellState()
    session_state = SessionState()
    outputs = []
    errors = []
    successes = []
    task = task_service.create_task(title="Task", goal="Goal")
    run = run_service.start_run(task.id)
    run_service.complete_run(
        run.id,
        step_count=2,
        last_usage={"total_tokens": 12},
        effective_skill_name="security-audit",
        effective_tools=["bash", "read_file"],
    )
    run_service.write_log(
        task_id=task.id,
        run_id=run.id,
        level=TaskLogLevel.INFO,
        message="tool_completed",
        payload={"tool_name": "read_file", "capability": "read", "result_summary": "sample"},
    )

    assert main_module.handle_task_command(
        f"/task runs {task.public_id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert main_module.handle_task_command(
        f"/task run {run.public_id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert main_module.handle_task_command(
        f"/task logs {task.public_id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any("R0001" in message for message in outputs)
    assert any("Failure Kind: -" in message for message in outputs)
    assert any("tool_name=read_file" in message for message in outputs)
    assert not errors
