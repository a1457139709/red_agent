from agent.settings import Settings
from agent.state import SessionState
from app.checkpoint_service import CheckpointService
from app.run_service import RunService
from app.task_service import TaskService
from main import ShellState, handle_task_command, parse_task_command
from models.run import TaskLogLevel
from models.task import TaskStatus
from runtime.task_runner import TaskRunner


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_parse_task_command():
    assert parse_task_command("/task list") == ("list", [])
    assert parse_task_command("/task logs abc 5") == ("logs", ["abc", "5"])
    assert parse_task_command("hello") is None


def test_handle_task_commands_create_list_show_and_logs(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service)
    session_state = SessionState()
    shell_state = ShellState()
    outputs = []
    errors = []
    successes = []

    responses = iter(["Refactor loop", "Add long-running task support"])

    def fake_input(_prompt):
        return next(responses)

    assert handle_task_command(
        "/task create",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
        input_func=fake_input,
    )

    task = task_service.list_tasks(limit=1)[0]
    run_service.write_log(task_id=task.id, level=TaskLogLevel.INFO, message="task_resumed")

    handle_task_command(
        "/task list",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        f"/task show {task.id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        f"/task logs {task.id} 5",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert successes
    assert any("Created task" in message for message in successes)
    assert any("Refactor loop" in message for message in outputs)
    assert any(task.id in message for message in outputs)
    assert any("task_resumed" in message for message in outputs)
    assert not errors


def test_handle_task_commands_resume_detach_and_complete(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service)
    session_state = SessionState()
    session_state.append_user_message("existing context")
    shell_state = ShellState()
    outputs = []
    errors = []
    successes = []
    task = task_service.create_task(title="Task", goal="Goal")
    checkpoint = CheckpointService.from_settings(settings).save_checkpoint(task_id=task.id, session_state=session_state)
    task_service.update_task_status(task.id, TaskStatus.PAUSED, last_checkpoint=checkpoint.id)

    fresh_session = SessionState()
    handle_task_command(
        f"/task resume {task.id}",
        shell_state=shell_state,
        session_state=fresh_session,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert shell_state.active_task_id == task.id
    assert fresh_session.history[0].content == "existing context"

    handle_task_command(
        "/task detach",
        shell_state=shell_state,
        session_state=fresh_session,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert shell_state.active_task_id is None
    assert task_service.require_task(task.id).status == TaskStatus.PAUSED

    handle_task_command(
        f"/task resume {task.id}",
        shell_state=shell_state,
        session_state=fresh_session,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        "/task complete",
        shell_state=shell_state,
        session_state=fresh_session,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert task_service.require_task(task.id).status == TaskStatus.COMPLETED
    assert shell_state.active_task_id is None
    assert not errors


def test_handle_task_commands_support_filters_search_status_and_help(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service)
    session_state = SessionState()
    shell_state = ShellState()
    outputs = []
    errors = []
    successes = []

    first = task_service.create_task(title="Weather skill", goal="Build weather skill")
    second = task_service.create_task(title="Security audit", goal="Audit configs")
    task_service.update_task_status(first.id, TaskStatus.RUNNING)

    handle_task_command(
        "/task list running 5",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        "/task recent 2",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        "/task find Weather 5",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        f"/task status {first.public_id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        "/task help",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any("Weather skill" in message and "running" in message for message in outputs)
    assert any(second.public_id in message and second.title in message for message in outputs)
    assert any("Task Status" in message and first.public_id in message and "Last Checkpoint:" in message for message in outputs)
    assert any("Task Commands" in message for message in outputs)
    assert any("/task recent [limit]" in message for message in outputs)
    assert any("Runs and Checkpoints" in message for message in outputs)
    assert any("latest" in message for message in outputs)
    assert not errors


def test_handle_task_commands_support_latest_alias_for_show_and_resume(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    checkpoint_service = CheckpointService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service)
    outputs = []
    errors = []
    successes = []

    task_service.create_task(title="Older", goal="Older goal")
    latest = task_service.create_task(title="Latest", goal="Latest goal")
    checkpoint_state = SessionState()
    checkpoint_state.append_user_message("restored context")
    checkpoint = checkpoint_service.save_checkpoint(task_id=latest.id, session_state=checkpoint_state)
    task_service.update_task_status(latest.id, TaskStatus.PAUSED, last_checkpoint=checkpoint.id)

    fresh_session = SessionState()
    shell_state = ShellState()
    handle_task_command(
        "/task show latest",
        shell_state=shell_state,
        session_state=fresh_session,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    handle_task_command(
        "/task resume latest",
        shell_state=shell_state,
        session_state=fresh_session,
        task_service=task_service,
        run_service=run_service,
        checkpoint_service=checkpoint_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any("Title:" in message and "Latest" in message for message in outputs)
    assert any(f"Resumed task {latest.public_id}" in message for message in successes)
    assert shell_state.active_task_public_id == latest.public_id
    assert fresh_session.history[0].content == "restored context"
    assert not errors


def test_help_command_renders_overview_topics_and_topic_help(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service)
    session_state = SessionState()
    shell_state = ShellState()
    outputs = []
    errors = []

    assert handle_task_command(
        "/task help",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
    )

    from main import handle_help_command

    assert handle_help_command("/help", text_output=outputs.append, error_output=errors.append)
    assert handle_help_command("/help skill", text_output=outputs.append, error_output=errors.append)
    assert handle_help_command("/help unknown", text_output=outputs.append, error_output=errors.append)

    assert any("Help Topics" in message and "/help task" in message for message in outputs)
    assert any("Task Commands" in message and "Runs and Checkpoints" in message for message in outputs)
    assert any("Skill Commands" in message and "/skill-name <prompt>" in message for message in outputs)
    assert any("Unknown help topic: unknown" in message and "Available topics: task, skill" in message for message in errors)
