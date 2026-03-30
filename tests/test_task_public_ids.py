from agent.settings import Settings
from agent.state import SessionState
from app.run_service import RunService
from app.task_service import TaskService
from main import ShellState, build_prompt, create_skill_service, handle_task_command
from models.task import TaskStatus
from runtime.task_runner import TaskRunner


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_task_service_assigns_public_ids_and_supports_public_lookup(tmp_path):
    settings = build_settings(tmp_path)
    service = TaskService.from_settings(settings)

    first = service.create_task(title="First", goal="One")
    second = service.create_task(title="Second", goal="Two")

    assert first.public_id == "T0001"
    assert second.public_id == "T0002"
    assert service.get_task(first.public_id) is not None
    assert service.get_task(first.public_id).id == first.id
    assert service.get_task(first.id[:8]) is not None
    assert service.get_task(first.id[:8]).id == first.id


def test_task_cli_uses_public_ids_for_render_and_binding(tmp_path):
    settings = build_settings(tmp_path)
    task_service = TaskService.from_settings(settings)
    run_service = RunService.from_settings(settings)
    task_runner = TaskRunner(task_service, run_service, create_skill_service())
    session_state = SessionState()
    shell_state = ShellState()
    outputs = []
    errors = []
    successes = []
    responses = iter(["Refactor loop", "Improve task UX", ""])

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
    checkpoint = run_service.save_checkpoint(task_id=task.id, session_state=session_state)
    task_service.update_task_status(task.id, TaskStatus.PAUSED, last_checkpoint=checkpoint.id)

    assert handle_task_command(
        f"/task show {task.public_id}",
        shell_state=shell_state,
        session_state=session_state,
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )
    assert handle_task_command(
        f"/task resume {task.public_id}",
        shell_state=shell_state,
        session_state=SessionState(),
        task_service=task_service,
        run_service=run_service,
        task_runner=task_runner,
        text_output=outputs.append,
        error_output=errors.append,
        success_output=successes.append,
    )

    assert any(f"Created task {task.public_id}" in message for message in successes)
    assert any(f"Task ID: {task.public_id}" in message for message in outputs)
    assert shell_state.active_task_public_id == task.public_id
    assert build_prompt(shell_state) == f"\ntask:{task.public_id} > "
    assert not errors
