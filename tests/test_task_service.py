from agent.settings import Settings
from app.task_service import TaskService
from models.task import TaskStatus


def build_settings(tmp_path):
    return Settings(
        openai_api_key="key",
        openai_api_base="https://example.com",
        openai_model="test-model",
        working_directory=tmp_path,
    )


def test_task_service_creates_and_loads_task(tmp_path):
    settings = build_settings(tmp_path)
    service = TaskService.from_settings(settings)

    task = service.create_task(
        title="Refactor loop",
        goal="Add durable task support",
        metadata={"source": "test"},
    )

    loaded = service.get_task(task.id)

    assert loaded is not None
    assert loaded.id == task.id
    assert loaded.title == "Refactor loop"
    assert loaded.status == TaskStatus.PENDING
    assert loaded.metadata["source"] == "test"
    assert settings.sqlite_path.exists()


def test_task_service_lists_tasks_by_recent_update(tmp_path):
    settings = build_settings(tmp_path)
    service = TaskService.from_settings(settings)

    first = service.create_task(title="Task one", goal="First goal")
    second = service.create_task(title="Task two", goal="Second goal")

    tasks = service.list_tasks()

    assert [task.id for task in tasks] == [second.id, first.id]




def test_task_service_filters_by_status_and_title_and_returns_latest(tmp_path):
    settings = build_settings(tmp_path)
    service = TaskService.from_settings(settings)

    first = service.create_task(title="Refactor loop", goal="First goal")
    second = service.create_task(title="Weather skill", goal="Second goal")
    service.update_task_status(first.id, TaskStatus.RUNNING)

    running = service.list_tasks(status=TaskStatus.RUNNING)
    weather = service.list_tasks(title_query="weather")
    latest_weather = service.get_latest_task(title_query="weather")

    assert [task.id for task in running] == [first.id]
    assert [task.id for task in weather] == [second.id]
    assert latest_weather is not None
    assert latest_weather.id == second.id

def test_task_service_updates_task_status(tmp_path):
    settings = build_settings(tmp_path)
    service = TaskService.from_settings(settings)
    task = service.create_task(title="Task one", goal="First goal")

    updated = service.update_task_status(
        task.id,
        TaskStatus.RUNNING,
        last_checkpoint="step-1",
    )

    loaded = service.get_task(task.id)

    assert updated.status == TaskStatus.RUNNING
    assert loaded is not None
    assert loaded.status == TaskStatus.RUNNING
    assert loaded.last_checkpoint == "step-1"


def test_task_service_raises_for_missing_task(tmp_path):
    settings = build_settings(tmp_path)
    service = TaskService.from_settings(settings)

    try:
        service.update_task_status("missing", TaskStatus.RUNNING)
    except ValueError as exc:
        assert "Task not found" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing task")
