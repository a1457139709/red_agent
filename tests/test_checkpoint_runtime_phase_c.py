import asyncio

from langchain_core.messages import AIMessage

import runtime.task_runner as task_runner_module
from agent.settings import Settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.run_service import RunService
from app.task_service import TaskService
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


def test_task_runner_run_prompt_persists_blob_backed_checkpoint(monkeypatch, tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    runner = TaskRunner(
        task_service,
        run_service,
        checkpoint_service=checkpoint_service,
    )
    executor = ToolExecutor({"fake_tool": FakeTool()})
    task = task_service.create_task(title="Task", goal="Do work")
    task, session_state = runner.resume_task(task.id)

    async def fake_agent_loop(question, state, tool_executor, current_settings):
        return {
            "status": "completed",
            "response": "done",
            "messages": [
                AIMessage(
                    content="done",
                    tool_calls=[],
                    usage_metadata={"input_tokens": 6, "output_tokens": 6, "total_tokens": 12},
                )
            ],
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr(task_runner_module, "agent_loop", fake_agent_loop)

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
    checkpoint = checkpoint_service.require_checkpoint_record(updated_task.last_checkpoint)

    assert updated_task.status == TaskStatus.RUNNING
    assert checkpoint.storage_kind == "file_blob"
    assert checkpoint.blob_encoding == "json+gzip"
    assert checkpoint.blob_path is not None
    assert (settings.app_data_dir / checkpoint.blob_path).exists()


def test_task_runner_resume_detach_and_complete_use_checkpoint_service(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    runner = TaskRunner(
        task_service,
        run_service,
        checkpoint_service=checkpoint_service,
    )

    original_state = SessionState()
    original_state.append_user_message("hello")
    task = task_service.create_task(title="Task", goal="Do work")

    initial_checkpoint = checkpoint_service.save_checkpoint(
        task_id=task.id,
        session_state=original_state,
    )
    task_service.update_task_status(task.id, TaskStatus.PAUSED, last_checkpoint=initial_checkpoint.id)

    resumed_task, restored_state = runner.resume_task(task.id)
    detached_task = runner.detach_task(task.id, restored_state)
    detach_checkpoint = checkpoint_service.require_checkpoint_record(detached_task.last_checkpoint)
    completed_task = runner.complete_task(task.id, restored_state)
    complete_checkpoint = checkpoint_service.require_checkpoint_record(completed_task.last_checkpoint)

    assert resumed_task.status == TaskStatus.RUNNING
    assert restored_state.history[0].content == "hello"
    assert detached_task.status == TaskStatus.PAUSED
    assert (settings.app_data_dir / detach_checkpoint.blob_path).exists()
    assert completed_task.status == TaskStatus.COMPLETED
    assert (settings.app_data_dir / complete_checkpoint.blob_path).exists()
