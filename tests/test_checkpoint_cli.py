from agent.settings import Settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.run_service import RunService
from app.task_service import TaskService
from main import ShellState, handle_task_command, print_help
from runtime.task_runner import TaskRunner


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_task_checkpoint_commands_render_metadata_and_help(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service, checkpoint_service=checkpoint_service)
    shell_state = ShellState()
    session_state = SessionState()
    outputs = []
    errors = []

    task = task_service.create_task(title="Task", goal="Goal")
    run = run_service.start_run(task.id)
    state = SessionState()
    state.append_user_message("hello")
    checkpoint = checkpoint_service.save_checkpoint(
        task_id=task.id,
        run_id=run.id,
        session_state=state,
    )

    assert handle_task_command(
        f"/task checkpoints {task.public_id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_task_command(
        f"/task checkpoint {checkpoint.id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
    )

    help_lines = []
    print_help(help_lines.append)

    assert any("CHECKPOINT" in message for message in outputs)
    assert any(checkpoint.id in message for message in outputs)
    assert any("Payload Size:" in message for message in outputs)
    assert any("History Message Count:" in message for message in outputs)
    assert all("blob_path" not in message for message in outputs)
    assert all("payload_digest" not in message for message in outputs)
    assert any("/task checkpoints <id> [n]" in message for message in help_lines)
    assert any("/task checkpoint <id>" in message for message in help_lines)
    assert not errors


def test_task_checkpoint_commands_handle_limit_and_missing_objects(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service, checkpoint_service=checkpoint_service)
    shell_state = ShellState()
    session_state = SessionState()
    outputs = []
    errors = []

    task = task_service.create_task(title="Task", goal="Goal")
    for index in range(3):
        state = SessionState()
        state.append_user_message(f"hello-{index}")
        checkpoint_service.save_checkpoint(task_id=task.id, session_state=state)

    assert handle_task_command(
        f"/task checkpoints {task.public_id} 2",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_task_command(
        "/task checkpoints missing-task",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
    )
    assert handle_task_command(
        "/task checkpoint missing-checkpoint",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
    )

    checkpoint_rows = [
        line
        for line in outputs[0].splitlines()
        if line.strip() and not line.startswith("Task:") and not line.startswith("CHECKPOINT")
    ]
    assert len(checkpoint_rows) == 2
    assert any("Task not found: missing-task" in message for message in errors)
    assert any("Checkpoint not found: missing-checkpoint" in message for message in errors)
