from __future__ import annotations

from agent.settings import Settings, get_settings
from models.task import Task, TaskStatus
from storage.sqlite import SQLiteStorage
from storage.tasks import TaskRepository


class TaskService:
    def __init__(self, repository: TaskRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "TaskService":
        settings = settings or get_settings()
        storage = SQLiteStorage(settings.sqlite_path)
        repository = TaskRepository(storage)
        return cls(repository, settings)

    def create_task(
        self,
        *,
        title: str,
        goal: str,
        workspace: str | None = None,
        session_id: str | None = None,
        skill_profile: str | None = None,
        priority: int = 0,
        metadata: dict | None = None,
    ) -> Task:
        task = Task.create(
            title=title,
            goal=goal,
            workspace=workspace or str(self.settings.working_directory),
            session_id=session_id,
            skill_profile=skill_profile,
            priority=priority,
            metadata=metadata,
        )
        return self.repository.create(task)

    def get_task(self, task_id: str) -> Task | None:
        return self.repository.get(task_id)

    def require_task(self, task_id: str) -> Task:
        task = self.repository.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        return task

    def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        title_query: str | None = None,
        limit: int | None = 50,
    ) -> list[Task]:
        return self.repository.list(status=status, title_query=title_query, limit=limit)

    def get_latest_task(
        self,
        *,
        status: TaskStatus | None = None,
        title_query: str | None = None,
    ) -> Task | None:
        tasks = self.repository.list(status=status, title_query=title_query, limit=1)
        if not tasks:
            return None
        return tasks[0]

    def save_task(self, task: Task) -> Task:
        return self.repository.update(task)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        last_checkpoint: str | None = None,
        last_error: str | None = None,
    ) -> Task:
        task = self.require_task(task_id)

        updated = task.with_status(
            status,
            last_checkpoint=last_checkpoint,
            last_error=last_error,
        )
        return self.repository.update(updated)
