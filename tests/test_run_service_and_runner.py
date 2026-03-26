import asyncio

import pytest
from langchain_core.messages import AIMessage

import runtime.task_runner as task_runner_module
from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.task_service import TaskService
from models.run import RunStatus, TaskLogLevel
from models.task import TaskStatus
from runtime.task_runner import TaskRunner
from tools.executor import ToolExecutor


class FakeTool:
    name = "fake_tool"

    def invoke(self, args):
        return "ok"


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_task_runner_persists_run_checkpoint_and_logs(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service)
    executor = ToolExecutor({"fake_tool": FakeTool()})
    task = task_service.create_task(title="Task", goal="Do work")
    task, session_state = runner.resume_task(task.id)

    async def fake_agent_loop(question, state, tool_executor, current_settings):
        return {
            "status": "completed",
            "response": "done",
            "messages": [AIMessage(content="done", tool_calls=[], usage_metadata={"input_tokens": 6, "output_tokens": 6, "total_tokens": 12})],
            "usage": {"total_tokens": 12},
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

    updated_task = task_service.require_task(task.id)
    logs = run_service.list_logs(task.id)
    run_ids = [entry.run_id for entry in logs if entry.run_id]
    persisted_run = run_service.get_run(run_ids[0])

    assert result["status"] == "completed"
    assert updated_task.status == TaskStatus.RUNNING
    assert updated_task.last_checkpoint is not None
    assert persisted_run is not None
    assert persisted_run.status == RunStatus.COMPLETED
    assert persisted_run.step_count == 1
    assert any(entry.message == "run_started" for entry in logs)
    assert any(entry.message == "run_completed" for entry in logs)
    assert any(entry.message == "checkpoint_saved" for entry in logs)


def test_task_runner_resume_restore_complete_and_block_future_resume(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service)
    original_state = SessionState()
    original_state.append_user_message("hello")

    task = task_service.create_task(title="Task", goal="Do work")
    checkpoint = run_service.save_checkpoint(task_id=task.id, session_state=original_state)
    task_service.update_task_status(task.id, TaskStatus.PAUSED, last_checkpoint=checkpoint.id)

    resumed_task, restored_state = runner.resume_task(task.id)
    completed_task = runner.complete_task(task.id, restored_state)

    assert resumed_task.status == TaskStatus.RUNNING
    assert restored_state.history[0].content == "hello"
    assert completed_task.status == TaskStatus.COMPLETED

    with pytest.raises(ValueError):
        runner.resume_task(task.id)


def test_task_runner_marks_failures_and_records_error_log(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    runner = TaskRunner(task_service, run_service)
    executor = ToolExecutor({"fake_tool": FakeTool()})
    task = task_service.create_task(title="Task", goal="Do work")
    task, session_state = runner.resume_task(task.id)

    async def failing_agent_loop(question, state, tool_executor, current_settings):
        raise RuntimeError("boom")

    monkeypatch.setattr(task_runner_module, "agent_loop", failing_agent_loop)

    with pytest.raises(RuntimeError):
        asyncio.run(
            runner.run_prompt(
                task_id=task.id,
                question="continue",
                session_state=session_state,
                tool_executor=executor,
                settings=settings,
            )
        )

    updated_task = task_service.require_task(task.id)
    logs = run_service.list_logs(task.id)
    failed_entries = [entry for entry in logs if entry.message == "run_failed"]
    failed_run = run_service.get_run(failed_entries[0].run_id)

    assert updated_task.status == TaskStatus.FAILED
    assert updated_task.last_error == "boom"
    assert failed_run is not None
    assert failed_run.status == RunStatus.FAILED
    assert any(entry.level == TaskLogLevel.ERROR and entry.message == "run_failed" for entry in logs)
